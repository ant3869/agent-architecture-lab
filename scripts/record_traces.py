"""Record the execution traces shown in the explorer. Deterministic: same code, same traces."""
from __future__ import annotations

from typing import Any

from agentlab.core.runtime import Meter, Runtime
from agentlab.core.trace import Tracer
from agentlab.core.types import SimulatedCrash
from agentlab.core.util import SimClock
from agentlab.durability.crash import CrashingTools, CrashSchedule
from agentlab.durability.journal import DurableSession
from agentlab.durability.stores import SQLiteJournal
from agentlab.loops.plan_execute import PlanExecuteLoop
from agentlab.loops.react import ReActLoop
from agentlab.loops.verified_graph import VerifiedGraphLoop
from agentlab.memory.context import Compaction
from agentlab.orchestration.handoff import HandoffSwarm
from agentlab.orchestration.supervisor import SupervisorWorkers
from agentlab.permissions.policy import ApprovalTools
from agentlab.recovery.policies import CircuitBreakerTools, RetryingTools
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import Task, evaluate, make_task
from agentlab.sim.world import FaultPlan, World
from agentlab.tools.registry import StaticRegistry, world_tools


def _pack(id: str, title: str, pattern: str, solution: str, description: str, task: Task, world: World, meter: Meter, tracer: Tracer, status: str) -> dict[str, Any]:
    out = evaluate(task, world)
    return {
        "id": id, "title": title, "pattern": pattern, "solution": solution, "description": description, "goal": task.goal,
        "summary": {"status": status, "outcome": out.reason, "steps": len(task.steps), "model_calls": meter.model_calls, "tool_calls": meter.tool_calls,
                    "backend_calls": len(world.calls), "tokens": meter.total_tokens, "peak_context": meter.peak_prompt_tokens, "sim_ms": world.clock.now_ms},
        "events": tracer.events,
    }


def _single(id, title, pattern, solution, description, loop_cls, task, profile, seed=1, faults=None, wrap=None, **loop_kw):
    clock = SimClock()
    world, meter, tracer = World(task, clock, faults), Meter(), Tracer(clock)
    tools = StaticRegistry(world_tools(world))
    if wrap:
        tools = wrap(tools, world)
    rt = Runtime(SimModel(profile, task, seed), tools, clock=clock, tracer=tracer, meter=meter)
    result = loop_cls(rt, **loop_kw).run(task.goal_message())
    return _pack(id, title, pattern, solution, description, task, world, meter, tracer, result.status)


def record_all() -> list[dict[str, Any]]:
    traces = []
    noisy = ModelProfile(slip_rate=0.2, silent_fraction=0.5, verifier_miss_rate=0.0)
    t = make_task(8, stages=1, lookups=3, moved=1)
    traces.append(_single("react-surprise", "ReAct recovers from a relocated key and a malformed call", "execution-loops", "react",
                          "One key has moved and the model slips once. Each error is simply the next observation.", ReActLoop, t, ModelProfile(slip_rate=0.2, silent_fraction=0.0), seed=2))
    traces.append(_single("plan-execute-replan", "Plan-and-Execute replans after a surprise", "execution-loops", "plan_execute",
                          "The plan is written before the relocated key is known. Execution fails at that step and the model replans the remainder.", PlanExecuteLoop, t, ModelProfile()))
    t2 = make_task(3, stages=2, lookups=2)
    traces.append(_single("verified-graph-repair", "Verified graph catches silent errors before a side effect", "execution-loops", "verified_graph",
                          "The model slips 20% of the time and half of the slips are silent. Follow the verify -> repair transitions.", VerifiedGraphLoop, t2, noisy, seed=1))
    traces.append(_single("react-silent-failure", "ReAct commits a silent error", "execution-loops", "react",
                          "Same task, same model and same slips as the verified-graph trace. Nothing reports the wrong call, so it flows into the write.", ReActLoop, t2, noisy, seed=1))

    t3 = make_task(5, stages=3, lookups=3)
    clock = SimClock()
    world, meter, tracer = World(t3, clock), Meter(), Tracer(clock)
    res = SupervisorWorkers(SimModel(ModelProfile(), t3), world_tools(world), clock=clock, meter=meter, tracer=tracer, pool={"data": 2, "math": 2, "ops": 1}, crash={"data-1": 2}, idempotent=True).run(t3)
    tr = _pack("supervisor-crash", "Supervisor reassigns work after a worker crash", "orchestration", "supervisor",
               "Two data workers, two math workers, one ops worker. data-1 dies after its second tool call; the supervisor notices by timeout and reassigns.", t3, world, meter, tracer, res.status)
    tr["timeline"], tr["summary"]["makespan_ms"] = res.timeline, res.makespan_ms
    traces.append(tr)

    t4 = make_task(5, stages=2, lookups=2)
    clock = SimClock()
    world, meter, tracer = World(t4, clock), Meter(), Tracer(clock)
    res = HandoffSwarm(SimModel(ModelProfile(), t4), world_tools(world), clock=clock, meter=meter, tracer=tracer).run(t4)
    traces.append(_pack("peer-handoff", "Peer handoff: the transcript travels", "orchestration", "handoff",
                        "Three specialists pass one conversation between them. Watch the size of each handoff message grow.", t4, world, meter, tracer, res.status))

    t5 = make_task(2, stages=2, lookups=2, notify_stages=True)
    clock = SimClock()
    world, meter, tracer = World(t5, clock), Meter(), Tracer(clock)
    schedule, journal, status = CrashSchedule([(6, "after"), (11, "after")]), SQLiteJournal(), "crashed"
    for process in range(1, 6):
        tracer.emit("note", "runtime", text=f"process {process} starts; journal holds {len(journal.load(t5.id))} records")
        session = DurableSession(journal, t5.id)
        rt = Runtime(session.model(SimModel(ModelProfile(), t5)), session.tools(CrashingTools(StaticRegistry(world_tools(world)), schedule)), clock=clock, tracer=tracer, meter=meter)
        try:
            status = ReActLoop(rt).run(t5.goal_message()).status
            break
        except SimulatedCrash as e:
            tracer.emit("note", "runtime", text=f"CRASH: {e}. In-memory state lost; the world keeps the effect.")
    traces.append(_pack("journal-recovery", "Journal replay across two crashes", "durable-execution", "journal",
                        "Both crashes land right after a non-idempotent send. Replayed calls are marked; the re-issued send is collapsed by its idempotency key.", t5, world, meter, tracer, status))

    t6 = make_task(1, stages=1, lookups=3, poisoned=True)
    clock = SimClock()
    world, meter, tracer = World(t6, clock), Meter(), Tracer(clock)
    gate = ApprovalTools(StaticRegistry(world_tools(world)))
    loop = ReActLoop(Runtime(SimModel(ModelProfile(injection_susceptibility=1.0), t6), gate, clock=clock, tracer=tracer, meter=meter))
    result = loop.run(t6.goal_message())
    while result.status == "interrupted":
        call = result.pending
        ok = call.args["to"] == "ops"
        tracer.emit("note", "reviewer", text=f"run paused for approval of {call.tool}({call.args}); reviewer decides: {'approve' if ok else 'deny'}")
        if ok:
            gate.grant(call)
        result = loop.run(t6.goal_message(), resume=result.history, pending=(call, ok))
    traces.append(_pack("approval-injection", "Human approval stops an injected exfiltration", "permissions", "approval",
                        "A looked-up record carries an instruction to send data to an outside recipient and the model obeys. The run pauses at each external call.", t6, world, meter, tracer, result.status))

    t7 = make_task(4, stages=4, lookups=3)
    traces.append(_single("compaction", "Compaction on a 29-step task", "context-memory", "compaction",
                          "When the context beyond the goal passes 600 tokens the older part is summarised. Look for the `summarize` model calls and the drop in prompt tokens after each.", ReActLoop, t7, ModelProfile(), memory=Compaction(600, keep_recent=4)))

    t8 = make_task(6, stages=2, lookups=3)

    def breaker(tools, world):
        full = StaticRegistry(world_tools(world, ("lookup", "lookup_replica", "compute", "write", "send")))
        return CircuitBreakerTools(RetryingTools(full, world.clock), world.clock, fallbacks={"lookup": "lookup_replica"})

    traces.append(_single("breaker-outage", "Circuit breaker rides out an outage", "failure-recovery", "breaker",
                          "The lookup backend is down from 2s to 60s. After three failures the breaker opens and reads go to the replica; the model never sees an error.", ReActLoop, t8, ModelProfile(), faults=FaultPlan(outages=[("lookup", 2000, 60000)]), wrap=breaker))
    return traces
