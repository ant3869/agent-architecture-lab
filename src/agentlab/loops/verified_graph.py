"""Verified state-machine loop: plan -> execute -> verify -> repair, as an explicit graph.

Control flow is code, not model output. The model fills three narrow roles (planner,
verifier, finisher) and the graph guarantees one invariant the other two loops cannot:

    no side-effecting tool call is executed until every unverified upstream step and the
    proposed call itself have passed an independent verification.

Built on `statemachine.StateGraph`, so each node boundary is a checkpoint.
"""
from __future__ import annotations

from typing import Any

from ..core.messages import assistant_message, rejection_message, tool_message, verdict_message
from ..core.runtime import Runtime
from ..core.types import Message
from ..memory.context import ContextPolicy, FullHistory
from ..statemachine.graph import END, Checkpointer, StateGraph
from .base import LoopResult, plan_refs, resolve_refs


class VerifiedGraphLoop:
    name = "verified_graph"

    def __init__(
        self,
        rt: Runtime,
        memory: ContextPolicy | None = None,
        verify: str = "effects",  # "effects": gate side effects only | "all": audit after every step
        max_repairs: int = 12,
        max_replans: int = 12,
        checkpointer: Checkpointer | None = None,
        thread_id: str = "run",
    ):
        if verify not in ("effects", "all"):
            raise ValueError("verify must be 'effects' or 'all'")
        self.rt = rt
        self.memory = memory or FullHistory()
        self.verify = verify
        self.max_repairs, self.max_replans = max_repairs, max_replans
        self.thread_id = thread_id
        self.transitions: list[tuple[str, str]] = []
        self._effects = {s.name for s in rt.tools.specs() if s.effect != "read"}
        g = StateGraph()
        g.add_node("plan", self._plan).add_edge("plan", "gate")
        g.add_node("gate", lambda s: None).add_router("gate", self._route_gate)
        g.add_node("verify", self._verify).add_router("verify", lambda s: s["verdict"])
        g.add_node("repair", self._repair).add_router("repair", self._after_replan)
        g.add_node("execute", self._execute).add_router("execute", lambda s: "replan" if s["failed_step"] else "gate")
        g.add_node("replan", self._replan).add_router("replan", self._after_replan)
        g.add_node("finalize", self._finalize).add_edge("finalize", END)
        g.set_entry("plan")
        self.graph = g.compile(checkpointer, on_transition=self._on_transition)

    # -- public -----------------------------------------------------------------
    def run(self, goal: Message) -> LoopResult:
        state = {
            "history": [goal], "plan": [], "cursor": 0, "results": {}, "executed": {}, "unverified": [],
            "cleared": "", "verdict": "", "bad": [], "failed_step": "", "replans": 0, "repairs": 0,
            "iterations": 0, "status": "", "detail": "",
        }
        with self.rt.tracer.span("verified_graph.run", self.rt.agent):
            return self._result(self.graph.run(state, self.thread_id))

    def resume(self) -> LoopResult:
        """Continue from the last checkpoint (after a crash or interrupt)."""
        with self.rt.tracer.span("verified_graph.resume", self.rt.agent):
            return self._result(self.graph.resume(self.thread_id))

    # -- nodes ------------------------------------------------------------------
    def _view(self, s: dict[str, Any]) -> list[Message]:
        return self.memory.view(s["history"], self.rt)

    def _plan(self, s: dict[str, Any], mode: str = "plan") -> dict[str, Any]:
        resp = self.rt.call_model(mode, self._view(s))
        return {"history": s["history"] + [assistant_message(resp)], "plan": list(resp.plan or []), "cursor": 0, "cleared": "", "failed_step": ""}

    def _route_gate(self, s: dict[str, Any]) -> str:
        if s["status"] == "failed":
            return END
        if s["cursor"] >= len(s["plan"]):
            return "verify" if s["unverified"] else "finalize"
        nxt = s["plan"][s["cursor"]]
        if nxt.tool in self._effects and s["cleared"] != nxt.step_id:
            return "verify"
        if self.verify == "all" and s["unverified"]:
            return "verify"
        return "execute"

    def _verify(self, s: dict[str, Any]) -> dict[str, Any]:
        proposed = None
        if s["cursor"] < len(s["plan"]) and s["plan"][s["cursor"]].tool in self._effects:
            proposed = resolve_refs(s["plan"][s["cursor"]], s["results"])
            if proposed is None:
                return {"verdict": END, "status": "failed", "detail": "unresolved reference in proposed effect"}
        resp = self.rt.call_model("verify", self._view(s), audit=list(s["unverified"]), proposed=proposed)
        invalid = list(resp.data["invalid"])
        if invalid:
            return {"verdict": "repair", "bad": self._closure(invalid, s["executed"])}
        if not resp.data["proposed_ok"]:
            assert proposed is not None
            return {"verdict": "repair", "bad": [], "history": s["history"] + [rejection_message(proposed)]}
        out: dict[str, Any] = {"unverified": [], "verdict": "execute" if s["cursor"] < len(s["plan"]) else "finalize"}
        if proposed is not None:
            out["cleared"] = proposed.step_id
        return out

    @staticmethod
    def _closure(invalid: list[str], executed: dict[str, Any]) -> list[str]:
        bad = list(invalid)
        grew = True
        while grew:
            grew = False
            for sid, call in executed.items():
                if sid not in bad and any(r in bad for r in plan_refs(call)):
                    bad.append(sid)
                    grew = True
        return bad

    def _repair(self, s: dict[str, Any]) -> dict[str, Any]:
        if s["repairs"] >= self.max_repairs:
            return {"status": "failed", "detail": "repair budget exhausted"}
        bad = s["bad"]
        history = s["history"] + ([verdict_message(bad)] if bad else [])
        patch = {
            "history": history,
            "results": {k: v for k, v in s["results"].items() if k not in bad},
            "executed": {k: v for k, v in s["executed"].items() if k not in bad},
            "unverified": [k for k in s["unverified"] if k not in bad],
            "repairs": s["repairs"] + 1,
            "bad": [],
        }
        return {**patch, **self._plan({**s, **patch}, "replan")}

    def _execute(self, s: dict[str, Any]) -> dict[str, Any]:
        planned = s["plan"][s["cursor"]]
        call = resolve_refs(planned, s["results"])
        if call is None:
            return {"status": "failed", "detail": f"unresolved reference in {planned.step_id}", "failed_step": ""}
        result = self.rt.call_tool(call)
        out: dict[str, Any] = {"history": s["history"] + [tool_message(call, result)], "iterations": s["iterations"] + 1, "cleared": ""}
        if not result.ok:
            return {**out, "failed_step": call.step_id}
        out["results"] = {**s["results"], call.step_id: result.output}
        out["executed"] = {**s["executed"], call.step_id: planned}
        if call.tool not in self._effects:
            out["unverified"] = s["unverified"] + [call.step_id]
        return {**out, "cursor": s["cursor"] + 1, "failed_step": ""}

    def _replan(self, s: dict[str, Any]) -> dict[str, Any]:
        if s["replans"] >= self.max_replans:
            return {"status": "failed", "detail": f"replan budget exhausted at {s['failed_step']}"}
        return {"replans": s["replans"] + 1, **self._plan(s, "replan")}

    @staticmethod
    def _after_replan(s: dict[str, Any]) -> str:
        return END if s["status"] == "failed" else "gate"

    def _finalize(self, s: dict[str, Any]) -> dict[str, Any]:
        resp = self.rt.call_model("finalize", self._view(s))
        return {"history": s["history"] + [assistant_message(resp)], "status": "final", "detail": resp.text}

    # -- plumbing ---------------------------------------------------------------
    def _on_transition(self, src: str, dst: str) -> None:
        self.transitions.append((src, dst))
        self.rt.tracer.emit("transition", self.rt.agent, src=src, dst=dst)

    @staticmethod
    def _result(s: dict[str, Any]) -> LoopResult:
        status = s["status"] or ("interrupted" if "__interrupt__" in s else "failed")
        return LoopResult(status, s["iterations"], s["replans"], s["repairs"], history=s["history"], detail=s["detail"])
