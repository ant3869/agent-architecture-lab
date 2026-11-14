"""Supervisor-worker orchestration (centralised, context-isolated, parallel).

The supervisor decomposes the task once, then code - not the model - schedules subtasks
onto specialist workers as their inputs become available. Each worker runs its own ReAct
loop in a fresh context with only its domain's tools and returns condensed facts.
Lineage: AutoGen group chat manager (arXiv:2308.08155), Magentic-One orchestrator
(arXiv:2411.04468), Anthropic's orchestrator-worker research system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.runtime import Meter, Runtime
from ..core.trace import Tracer
from ..core.types import Model, SimulatedCrash, ToolExecutor
from ..core.util import SimClock
from ..durability.crash import CrashingTools, CrashSchedule
from ..loops.react import ReActLoop
from ..recovery.policies import IdempotentTools
from ..sim.tasks import Task
from ..tools.registry import ScopedRegistry, StaticRegistry, Tool
from .bus import AgentCard, Envelope, MessageBus


@dataclass
class OrchestrationResult:
    status: str  # final | failed
    makespan_ms: int = 0  # wall-clock with parallel workers (virtual-time schedule)
    work_ms: int = 0  # sum of all agent time
    messages: int = 0
    message_tokens: int = 0
    handoffs: int = 0
    reassignments: int = 0
    detail: str = ""
    timeline: list[dict[str, Any]] = field(default_factory=list)


class SupervisorWorkers:
    name = "supervisor"

    def __init__(
        self,
        model: Model,
        tools: list[Tool],
        *,
        clock: SimClock,
        meter: Meter | None = None,
        tracer: Tracer | None = None,
        pool: dict[str, int] | None = None,
        crash: dict[str, int] | None = None,
        idempotent: bool = False,
        respawn: bool = True,
        worker_timeout_ms: int = 5000,
        max_attempts: int = 3,
        worker_max_iters: int = 60,
    ):
        self.model, self.tools, self.clock = model, tools, clock
        self.meter = meter or Meter()
        self.tracer = tracer or Tracer(clock, enabled=False)
        self.bus = MessageBus(clock, self.tracer)
        self.crash = {w: CrashSchedule([(n, "after")]) for w, n in (crash or {}).items()}
        self.idempotent, self.respawn = idempotent, respawn
        self.worker_timeout_ms, self.max_attempts, self.worker_max_iters = worker_timeout_ms, max_attempts, worker_max_iters
        self._spawned = 0
        self.bus.register(AgentCard("supervisor", ("coordinate",)))
        for domain, n in (pool or {"data": 1, "math": 1, "ops": 1}).items():
            for i in range(1, n + 1):
                self.bus.register(AgentCard(f"{domain}-{i}", (domain,)))

    def _worker_tools(self, name: str, domain: str, task: Task) -> ToolExecutor:
        tools: ToolExecutor = ScopedRegistry(self.tools, [domain])  # least privilege: own domain only
        if name in self.crash:
            tools = CrashingTools(tools, self.crash[name])
        if self.idempotent:
            tools = IdempotentTools(tools, namespace=task.id)
        return tools

    def _run_worker(self, name: str, sub: dict[str, Any], task: Task, facts: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        goal = task.goal_message(assigned=sub["steps"], facts={k: facts[k] for k in sub["needs"]})
        self.bus.send(Envelope("supervisor", name, "task", sub["id"], {"steps": sub["steps"]}, goal.content))
        rt = Runtime(self.model, self._worker_tools(name, sub["domain"], task), clock=self.clock, tracer=self.tracer, meter=self.meter, agent=name)
        with self.tracer.span("worker.run", name, subtask=sub["id"]):
            result = ReActLoop(rt, max_iters=self.worker_max_iters).run(goal)
        produced = {m.meta["step_id"]: m.meta["output"] for m in result.history if m.role == "tool" and m.meta.get("ok") and m.meta["step_id"] in sub["steps"]}
        ok = result.status == "final" and all(s in produced for s in sub["steps"])
        text = "Result: " + ", ".join(f"{k}={v}" for k, v in produced.items())
        self.bus.send(Envelope(name, "supervisor", "result", sub["id"], {"state": "completed" if ok else "failed"}, text))
        return ("completed" if ok else "failed"), produced

    def run(self, task: Task) -> OrchestrationResult:
        t_start = self.clock.now_ms
        sup = Runtime(self.model, StaticRegistry([]), clock=self.clock, tracer=self.tracer, meter=self.meter, agent="supervisor")
        res = OrchestrationResult("failed")
        with self.tracer.span("supervisor.run", "supervisor"):
            goal = task.goal_message()
            plan = sup.call_model("decompose", [goal])
            pending: list[dict[str, Any]] = list(plan.data["subtasks"])
            owner = {s: sub["id"] for sub in pending for s in sub["steps"]}
            t0 = self.clock.now_ms
            facts: dict[str, Any] = {}
            finish: dict[str, int] = {}
            free_at: dict[str, int] = {}
            while pending:
                ready = [s for s in pending if all(n in facts for n in s["needs"])]
                if not ready:
                    res.detail = "deadlock: no subtask has its inputs"
                    return self._finish(res, t_start, t_start)
                for sub in ready:
                    pending.remove(sub)
                    earliest = max([finish[owner[n]] for n in sub["needs"]] or [t0])
                    state = "failed"
                    for _ in range(self.max_attempts):
                        live = self.bus.resolve(sub["domain"])
                        if not live and self.respawn:
                            self._spawned += 1
                            live = [f"{sub['domain']}-r{self._spawned}"]
                            self.bus.register(AgentCard(live[0], (sub["domain"],)))
                        if not live:
                            break
                        worker = min(live, key=lambda w: free_at.get(w, t0))
                        start = max(earliest, free_at.get(worker, t0))
                        before = self.clock.now_ms
                        try:
                            state, produced = self._run_worker(worker, sub, task, facts)
                        except SimulatedCrash:
                            self.clock.advance(self.worker_timeout_ms)  # the supervisor notices by timeout
                            self.bus.mark_down(worker)
                            res.reassignments += 1
                            earliest = start + (self.clock.now_ms - before)
                            res.timeline.append({"subtask": sub["id"], "worker": worker, "start": start - t0, "end": earliest - t0, "state": "crashed"})
                            continue
                        end = start + (self.clock.now_ms - before)
                        free_at[worker] = end
                        res.timeline.append({"subtask": sub["id"], "worker": worker, "start": start - t0, "end": end - t0, "state": state})
                        if state == "completed":
                            facts.update(produced)
                            finish[sub["id"]] = end
                            break
                        earliest = end
                        res.reassignments += 1
                    if state != "completed":
                        res.detail = f"subtask {sub['id']} could not be completed"
                        return self._finish(res, t_start, max(finish.values(), default=t0))
            before = self.clock.now_ms
            sup.call_model("finalize", [goal])
            res.status = "final"
            return self._finish(res, t_start, max(finish.values(), default=t0) + (self.clock.now_ms - before))

    def _finish(self, res: OrchestrationResult, t_start: int, t_end_virtual: int) -> OrchestrationResult:
        res.makespan_ms = t_end_virtual - t_start
        res.work_ms = self.clock.now_ms - t_start
        res.messages = len(self.bus.log)
        res.message_tokens = self.bus.message_tokens
        return res
