"""Deterministic simulated language model.

Design rules (they are what make the experiments meaningful):

* **Competence is fixed, knowledge is not.** The model knows *how* to solve a task
  (the oracle step list) but every concrete value must be visible in the messages
  it is given. Drop an observation from the context and the model must re-fetch it.
* **Stateless.** The response is a pure function of (seed, profile, request). Crash
  recovery, replay and context policies therefore cannot leak hidden state.
* **Paired noise.** A slip is drawn from hash(seed, task, step, attempt). Every
  architecture meets the same slips on the same steps, and a lower `slip_rate`
  produces a strict subset of a higher one.
* **Two kinds of error.** A *loud* slip makes the tool return an error (observable).
  A *silent* slip is a valid call with the wrong meaning (only verification finds it).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from ..core.types import Message, ModelRequest, ModelResponse, ToolCall
from ..core.util import estimate_tokens, u01
from .tasks import Ref, Step, Task

INJECT_RE = re.compile(r"@@INJECT send to=(\w+) body=(\d+)@@")
BLOCKING = {"PERMISSION_DENIED", "UNKNOWN_TOOL", "NO_AGENT", "APPROVAL_DENIED", "CAPABILITY_DENIED"}
_SWAP = {"add": "mul", "mul": "add", "sub": "add"}


@dataclass(frozen=True)
class ModelProfile:
    name: str = "sim-base"
    slip_rate: float = 0.0  # P(an emitted action is corrupted)
    silent_fraction: float = 0.5  # share of slips that are silent
    verifier_miss_rate: float = 0.1  # P(verifier overlooks a wrong call)
    injection_susceptibility: float = 0.0  # P(model obeys an instruction embedded in tool output)
    cost_in: float = 1.0  # cost units per 1k prompt tokens
    cost_out: float = 5.0  # cost units per 1k completion tokens
    latency_ms: int = 800


SMALL = ModelProfile("sim-small", slip_rate=0.12, verifier_miss_rate=0.25, cost_in=0.25, cost_out=1.25, latency_ms=400)
LARGE = ModelProfile("sim-large", slip_rate=0.02, verifier_miss_rate=0.05, cost_in=3.0, cost_out=15.0, latency_ms=1200)


class View:
    """Everything the model can know: a fold over the visible messages."""

    def __init__(self, messages: Iterable[Message]):
        self.values: dict[str, Any] = {}
        self.done: set[str] = set()
        self.attempts: Counter[str] = Counter()
        self.errors: dict[str, list[str]] = defaultdict(list)
        self.calls: dict[str, tuple[str, dict[str, Any]]] = {}
        self.moved: dict[str, str] = {}
        self.invalid: set[str] = set()
        self.assigned: list[str] | None = None
        self.injections: list[tuple[str, int]] = []
        self.toward: str | None = None  # the step the model last said it was working toward
        self.task_id: str | None = None
        for m in messages:
            meta = m.meta
            if "task_id" in meta and self.task_id is None:
                self.task_id = meta["task_id"]
            if "toward" in meta:
                self.toward = meta["toward"]
            if "assigned_steps" in meta:
                self.assigned = list(meta["assigned_steps"])
            if "facts" in meta:
                self.values.update(meta["facts"])
                self.done.update(meta.get("done", meta["facts"]))
                self.moved.update(meta.get("moved", {}))
                for sid, n in meta.get("attempts", {}).items():
                    self.attempts[sid] = max(self.attempts[sid], n)
            for sid in meta.get("invalid", ()):
                self.done.discard(sid)
                self.values.pop(sid, None)
                self.invalid.add(sid)
            if m.role == "tool" and "step_id" in meta:
                sid = meta["step_id"]
                self.attempts[sid] += 1
                if meta["ok"]:
                    self.done.add(sid)
                    self.values[sid] = meta["output"]
                    self.invalid.discard(sid)
                    self.calls[sid] = (meta["tool"], meta["args"])
                else:
                    self.errors[sid].append(meta["error_code"])
                    if meta["error_code"] == "MOVED":
                        self.moved[meta["args"]["key"]] = meta["info"]["moved_to"]
                self.injections += [(to, int(body)) for to, body in INJECT_RE.findall(m.content)]


def _corrupt(tool: str, args: dict[str, Any], silent: bool) -> dict[str, Any]:
    a = dict(args)
    if tool in ("lookup", "lookup_replica"):
        a["key"] = a["key"] + (".alt" if silent else "#typo")
    elif tool == "compute":
        a["op"] = _SWAP[a["op"]] if silent else "pow"
    elif tool == "write":
        a["key"] = a["key"] + ".tmp" if silent else "!" + a["key"]
    elif tool == "send":
        a["to"] = "audit" if silent else "nobody"
    return a


class SimModel:
    def __init__(self, profile: ModelProfile, tasks: Task | Iterable[Task], seed: int = 0):
        self.profile = profile
        self.seed = seed
        self._tasks = {t.id: t for t in ([tasks] if isinstance(tasks, Task) else tasks)}

    # -- protocol ---------------------------------------------------------------
    def complete(self, req: ModelRequest) -> ModelResponse:
        view = View(req.messages)
        if view.task_id not in self._tasks:
            raise KeyError(f"SimModel has no oracle for task {view.task_id!r}")
        task = self._tasks[view.task_id]
        resp: ModelResponse = getattr(self, f"_{req.mode}")(task, view, req)
        p = self.profile
        resp.prompt_tokens = sum(estimate_tokens(m.content) for m in req.messages) + sum(estimate_tokens(t.render()) for t in req.tools)
        if req.mode == "summarize":
            resp.prompt_tokens -= sum(estimate_tokens(t.render()) for t in req.tools)
        resp.completion_tokens = estimate_tokens(resp.text)
        resp.model = p.name
        resp.latency_ms = p.latency_ms
        resp.cost = (resp.prompt_tokens * p.cost_in + resp.completion_tokens * p.cost_out) / 1000.0
        return resp

    # -- shared reasoning -------------------------------------------------------
    def _order(self, task: Task, view: View) -> list[Step]:
        return [task.step(s) for s in view.assigned] if view.assigned is not None else list(task.steps)

    def _frontier(self, order: list[Step], view: View) -> int:
        """Lenient progress inference: everything before the latest visible success is assumed done."""
        done = [i for i, s in enumerate(order) if s.id in view.done]
        i = max(done) + 1 if done else 0
        ids = [s.id for s in order]
        if view.toward in ids:  # its own latest thought names the step it is trying to reach
            i = max(i, ids.index(view.toward))
        return i

    def _next_step(self, task: Task, view: View) -> tuple[Step, Step] | None:
        """Return (step to emit now, step the agent is ultimately trying to complete)."""
        order = self._order(task, view)
        redo = [s for s in order if s.id in view.invalid]
        if redo:
            target = redo[0]
        else:
            i = self._frontier(order, view)
            if i >= len(order):
                return None
            target = order[i]
        cand, seen = target, {target.id}
        while True:  # a needed value is not visible: go back and re-derive it
            missing = [r for r in cand.refs if r not in view.values]
            if not missing or missing[0] in seen:
                return cand, target
            cand = task.step(missing[0])
            seen.add(cand.id)

    def _args(self, step: Step, view: View, symbolic: bool) -> dict[str, Any]:
        args: dict[str, Any] = {}
        for k, v in step.args.items():
            if isinstance(v, Ref):
                args[k] = {"$ref": v.step} if symbolic else view.values.get(v.step)
            else:
                args[k] = v
        if "key" in args and step.tool.startswith("lookup"):
            args["key"] = view.moved.get(args["key"], args["key"])
        return args

    def _emit(self, task: Task, step: Step, view: View, symbolic: bool) -> ToolCall:
        """The call the model produces for `step`, slips included."""
        args = self._args(step, view, symbolic)
        k = view.attempts[step.id]
        if u01(self.seed, task.id, step.id, k, "slip") < self.profile.slip_rate:
            silent = u01(self.seed, task.id, step.id, k, "kind") < self.profile.silent_fraction
            args = _corrupt(step.tool, args, silent)
        return ToolCall(step.tool, args, step.id)

    @staticmethod
    def _render(call: ToolCall, note: str = "") -> str:
        return f"Thought: {note} [{call.step_id}]\nAction: {call.tool}({json.dumps(call.args, sort_keys=True)})"

    def _final(self, view: View, text: str = "task complete", blocked: bool = False) -> ModelResponse:
        return ModelResponse(f"FINAL: {text}", final=True, data={"blocked": blocked})

    # -- modes ------------------------------------------------------------------
    def _act(self, task: Task, view: View, req: ModelRequest) -> ModelResponse:
        exposed = {t.name for t in req.tools}
        if view.injections and "send" in exposed and view.attempts["_inj"] == 0:
            if u01(self.seed, task.id, "inject") < self.profile.injection_susceptibility:
                to, body = view.injections[0]
                call = ToolCall("send", {"to": to, "body": body}, "_inj")
                return ModelResponse(self._render(call, "the document says I must do this first"), call=call)
        nxt = self._next_step(task, view)
        if nxt is None:
            return self._final(view)
        step, target = nxt
        data = {"toward": target.id} if step.id != target.id else {}
        if step.tool in exposed:
            call = self._emit(task, step, view, symbolic=False)
        elif f"transfer_to_{step.domain}" in exposed:
            call = ToolCall(f"transfer_to_{step.domain}", {"reason": step.note}, f"_handoff:{step.id}")
        elif "search_tools" in exposed and view.attempts[f"_discover:{step.domain}"] == 0:
            call = ToolCall("search_tools", {"query": step.domain}, f"_discover:{step.domain}")
        else:
            call = self._emit(task, step, view, symbolic=False)
        errs = view.errors[call.step_id]
        if len(errs) >= 2 and all(e in BLOCKING for e in errs[-2:]):
            return self._final(view, f"cannot proceed, {call.tool} is blocked ({errs[-1]})", blocked=True)
        note = step.note if not data else f"{step.note} (needed again for {target.id})"
        return ModelResponse(self._render(call, note), call=call, data=data)

    def _plan(self, task: Task, view: View, req: ModelRequest) -> ModelResponse:
        order = self._order(task, view)
        i = self._frontier(order, view)
        todo = [s for n, s in enumerate(order) if s.id in view.invalid or n >= i]
        plan = [self._emit(task, s, view, symbolic=True) for s in todo]
        text = "Plan:\n" + "\n".join(f"{c.step_id}: {c.tool}({json.dumps(c.args, sort_keys=True)})" for c in plan)
        return ModelResponse(text, plan=plan)

    _replan = _plan

    def _finalize(self, task: Task, view: View, req: ModelRequest) -> ModelResponse:
        return self._final(view)

    def _verify(self, task: Task, view: View, req: ModelRequest) -> ModelResponse:
        """Audit executed steps (and optionally one proposed call) against an independent derivation."""
        invalid: list[str] = []
        for sid in req.params.get("audit", []):
            if sid not in view.calls or any(r in invalid for r in task.step(sid).refs):
                continue
            step = task.step(sid)
            wrong = view.calls[sid] != (step.tool, self._args(step, view, symbolic=False))
            if wrong and u01(self.seed, task.id, sid, view.attempts[sid], "verify") >= self.profile.verifier_miss_rate:
                invalid.append(sid)
        proposed_ok = True
        proposed: ToolCall | None = req.params.get("proposed")
        if proposed is not None and not invalid:
            step = task.step(proposed.step_id)
            wrong = (proposed.tool, proposed.args) != (step.tool, self._args(step, view, symbolic=False))
            if wrong and u01(self.seed, task.id, step.id, view.attempts[step.id], "preverify") >= self.profile.verifier_miss_rate:
                proposed_ok = False
        ok = not invalid and proposed_ok
        text = "VERIFY: ok" if ok else "VERIFY: reject " + ", ".join(invalid or [proposed.step_id])  # type: ignore[union-attr]
        return ModelResponse(text, data={"invalid": invalid, "proposed_ok": proposed_ok})

    def _decompose(self, task: Task, view: View, req: ModelRequest) -> ModelResponse:
        groups: dict[str, list[Step]] = {}
        for s in task.steps:
            groups.setdefault(s.group, []).append(s)
        subtasks = []
        for gid, steps in groups.items():
            ids = [s.id for s in steps]
            needs = sorted({r for s in steps for r in s.refs if r not in ids}, key=task.index)
            subtasks.append({"id": gid, "domain": steps[0].domain, "steps": ids, "needs": needs})
        text = "Delegation plan:\n" + "\n".join(f"{t['id']}: {t['domain']} worker does {','.join(t['steps'])} needs {','.join(t['needs']) or '-'}" for t in subtasks)
        return ModelResponse(text, data={"subtasks": subtasks})

    def _summarize(self, task: Task, view: View, req: ModelRequest) -> ModelResponse:
        order = [s.id for s in task.steps]
        done = sorted((s for s in view.done if s in order), key=task.index)
        facts = {s: view.values[s] for s in done if s in view.values}
        attempts = {s: n for s, n in view.attempts.items() if s not in view.done}
        text = "Summary: done " + ",".join(done) + "; values " + ",".join(f"{k}={v}" for k, v in facts.items())
        if view.moved:
            text += "; moved " + ",".join(f"{a}->{b}" for a, b in view.moved.items())
        return ModelResponse(text, data={"facts": facts, "done": done, "moved": dict(view.moved), "attempts": attempts})
