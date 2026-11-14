"""Peer-to-peer handoff orchestration (decentralised, one active agent, shared transcript).

There is no coordinator. Whichever specialist holds the conversation acts until the next
step is outside its tools, then calls `transfer_to_<skill>`; the full transcript moves
with the baton. Lineage: OpenAI Swarm and the Agents SDK ("handoffs are represented as
tools to the LLM"), AutoGen Swarm, LangGraph swarm.
"""
from __future__ import annotations

from ..core.messages import assistant_message, tool_message
from ..core.runtime import Meter, Runtime
from ..core.trace import Tracer
from ..core.types import Message, Model, SimulatedCrash, ToolCall, ToolExecutor, ToolResult, ToolSpec
from ..core.util import SimClock
from ..durability.crash import CrashingTools, CrashSchedule
from ..recovery.policies import IdempotentTools
from ..sim.tasks import Task
from ..tools.registry import ScopedRegistry, Tool
from .bus import AgentCard, Envelope, MessageBus
from .supervisor import OrchestrationResult

SKILLS = ("data", "math", "ops")


class _PeerTools:
    """A peer's own domain tools plus one transfer tool per other skill."""

    def __init__(self, inner: ToolExecutor, own: str):
        self.inner = inner
        self.transfers = [
            ToolSpec(f"transfer_to_{s}", f"Hand the conversation to the {s} specialist.", {"reason": "string"}, "read", True, "meta") for s in SKILLS if s != own
        ]

    def specs(self) -> list[ToolSpec]:
        return self.inner.specs() + self.transfers

    def execute(self, call: ToolCall) -> ToolResult:
        return self.inner.execute(call)


class HandoffSwarm:
    name = "handoff"

    def __init__(
        self,
        model: Model,
        tools: list[Tool],
        *,
        clock: SimClock,
        meter: Meter | None = None,
        tracer: Tracer | None = None,
        replicas: dict[str, int] | None = None,
        crash: dict[str, int] | None = None,  # agent name -> dies right after its n-th tool call is applied
        redeliver: bool = False,  # keep the last handoff envelope durable and re-deliver it to a replica
        idempotent: bool = False,
        timeout_ms: int = 5000,
        max_iters: int = 300,
    ):
        self.model, self.tools, self.clock = model, tools, clock
        self.meter = meter or Meter()
        self.tracer = tracer or Tracer(clock, enabled=False)
        self.bus = MessageBus(clock, self.tracer)
        self.crash = {a: CrashSchedule([(n, "after")]) for a, n in (crash or {}).items()}
        self.redeliver, self.idempotent = redeliver, idempotent
        self.timeout_ms, self.max_iters = timeout_ms, max_iters
        for skill in SKILLS:
            for i in range(1, (replicas or {}).get(skill, 1) + 1):
                self.bus.register(AgentCard(f"{skill}-{i}", (skill,)))

    def _runtime(self, name: str, task: Task) -> Runtime:
        skill = self.bus.cards[name].skills[0]
        tools: ToolExecutor = ScopedRegistry(self.tools, [skill])
        if name in self.crash:
            tools = CrashingTools(tools, self.crash[name])
        if self.idempotent:
            tools = IdempotentTools(tools, namespace=task.id)
        return Runtime(self.model, _PeerTools(tools, skill), clock=self.clock, tracer=self.tracer, meter=self.meter, agent=name)

    def run(self, task: Task) -> OrchestrationResult:
        t_start = self.clock.now_ms
        res = OrchestrationResult("failed")
        history: list[Message] = [task.goal_message()]
        baton = list(history)  # transcript as of the last handoff: all a replica would receive
        active = self.bus.resolve(task.steps[0].domain)[0]
        runtimes: dict[str, Runtime] = {}
        with self.tracer.span("handoff.run", active):
            for _ in range(self.max_iters):
                rt = runtimes.setdefault(active, self._runtime(active, task))
                resp = rt.call_model("act", history)
                history.append(assistant_message(resp))
                if resp.final:
                    res.status = "blocked" if resp.data.get("blocked") else "final"
                    res.detail = resp.text
                    break
                call = resp.call
                assert call is not None
                if call.tool.startswith("transfer_to_"):
                    peers = self.bus.resolve(call.tool.removeprefix("transfer_to_"))
                    if not peers:
                        result = ToolResult(False, error_code="NO_AGENT", error="no live agent offers that skill")
                    else:
                        result = ToolResult(True, {"now_active": peers[0]})
                        history.append(tool_message(call, result))
                        self.bus.send(Envelope(active, peers[0], "handoff", task.id, {"messages": len(history)}, "\n".join(m.content for m in history)))
                        res.handoffs += 1
                        active, baton = peers[0], list(history)
                        continue
                else:
                    try:
                        result = rt.call_tool(call)
                    except SimulatedCrash:  # the baton holder died; nobody else has the transcript
                        skill = self.bus.cards[active].skills[0]
                        self.bus.mark_down(active)
                        self.clock.advance(self.timeout_ms)
                        peers = self.bus.resolve(skill)
                        if not self.redeliver or not peers:
                            res.detail = f"baton lost: {active} crashed" + ("" if self.redeliver else " and handoffs are not durable")
                            break
                        res.reassignments += 1
                        active, history = peers[0], list(baton)
                        continue
                history.append(tool_message(call, result))
            else:
                res.detail = "max iterations"
        res.work_ms = res.makespan_ms = self.clock.now_ms - t_start  # strictly sequential
        res.messages, res.message_tokens = len(self.bus.log), self.bus.message_tokens
        return res
