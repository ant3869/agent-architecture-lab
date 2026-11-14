import pytest

from agentlab.core.runtime import Meter
from agentlab.core.trace import Tracer
from agentlab.core.util import SimClock
from agentlab.eval.harness import run_loop
from agentlab.orchestration.bus import AgentCard, AgentUnavailable, Envelope, MessageBus
from agentlab.orchestration.handoff import HandoffSwarm
from agentlab.orchestration.supervisor import SupervisorWorkers
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import world_tools

T = make_task(5, stages=4, lookups=3)
TN = make_task(5, stages=3, lookups=2, notify_stages=True)


def orch(cls, task=T, profile=None, trace=False, **kw):
    clock = SimClock()
    world, meter, tracer = World(task, clock), Meter(), Tracer(clock, enabled=trace)
    o = cls(SimModel(profile or ModelProfile(), task, 1), world_tools(world), clock=clock, meter=meter, tracer=tracer, **kw)
    res = o.run(task)
    return o, res, world, meter, evaluate(task, world), tracer


def test_bus_discovery_delivery_and_failure():
    bus = MessageBus()
    for name, skill in (("a", "data"), ("b", "data"), ("c", "math")):
        bus.register(AgentCard(name, (skill,)))
    assert bus.resolve("data") == ["a", "b"] and bus.resolve("ops") == []
    bus.mark_down("a")
    assert bus.resolve("data") == ["b"]
    env = bus.send(Envelope("c", "b", "task", "t1", text="do the thing"))
    assert (env.seq, env.tokens, bus.message_tokens) == (0, 3, 3)
    with pytest.raises(AgentUnavailable, match="down"):
        bus.send(Envelope("c", "a", "task", "t1"))
    with pytest.raises(AgentUnavailable, match="unknown"):
        bus.send(Envelope("c", "zzz", "task", "t1"))
    with pytest.raises(ValueError):
        bus.register(AgentCard("b", ("x",)))


def test_supervisor_completes_and_isolates_worker_context():
    _, res, _, meter, out, _ = orch(SupervisorWorkers)
    single = run_loop("react", T)
    assert res.status == "final" and out.success
    assert meter.peak_prompt_tokens < single["peak_context"] / 3
    assert meter.total_tokens < single["total_tokens"] / 2
    assert meter.model_calls > single["model_calls"], "coordination costs calls"
    assert res.messages == 2 * len({s.group for s in T.steps}), "one task + one result envelope per subtask"


def test_workers_get_only_their_own_domain_tools():
    o, *_ , tracer = orch(SupervisorWorkers, trace=True)
    by_agent = {}
    for e in tracer.events:
        if e["kind"] == "tool_result":
            by_agent.setdefault(e["agent"].split("-")[0], set()).add(e["data"]["call"]["tool"])
    assert by_agent == {"data": {"lookup"}, "math": {"compute"}, "ops": {"write", "send"}}
    assert [s.name for s in o._worker_tools("math-1", "math", T).specs()] == ["compute"]


def test_parallel_pool_shortens_makespan_but_not_total_work():
    _, one, *_ = orch(SupervisorWorkers)
    _, three, *_ = orch(SupervisorWorkers, pool={"data": 3, "math": 3, "ops": 3})
    assert three.makespan_ms < one.makespan_ms < one.work_ms and three.work_ms == one.work_ms
    for a in three.timeline:
        for b in three.timeline:
            if a is not b and a["worker"] == b["worker"]:
                assert a["end"] <= b["start"] or b["end"] <= a["start"], "a worker never runs two subtasks at once"
    starts = {r["subtask"]: r for r in three.timeline}
    assert starts["st1.math"]["start"] >= starts["st1.data"]["end"], "dependencies are respected"


def test_supervisor_reassigns_after_a_worker_crash():
    _, res, world, _, out, _ = orch(SupervisorWorkers, crash={"data-1": 2})
    assert res.status == "final" and out.success and res.reassignments == 1
    assert [r["state"] for r in res.timeline][:2] == ["crashed", "completed"]
    _, res, *_ , out, _ = orch(SupervisorWorkers, crash={"data-1": 2}, respawn=False)
    assert res.status == "failed" and "could not be completed" in res.detail


def test_reassigned_side_effects_duplicate_unless_idempotent():
    _, res, world, _, out, _ = orch(SupervisorWorkers, task=TN, crash={"ops-1": 2})
    assert out.reason == "duplicate_effect" and res.reassignments == 1
    _, res, world, _, out, _ = orch(SupervisorWorkers, task=TN, crash={"ops-1": 2}, idempotent=True)
    assert out.success and any(c["deduped"] for c in world.calls)


def test_handoff_completes_with_one_active_agent_and_a_travelling_transcript():
    o, res, _, meter, out, tracer = orch(HandoffSwarm, trace=True)
    single = run_loop("react", T)
    assert res.status == "final" and out.success and res.handoffs == res.messages > 8
    assert meter.model_calls == single["model_calls"] + res.handoffs, "each handoff is one extra model turn"
    assert meter.total_tokens > single["total_tokens"]
    sizes = [e.payload["messages"] for e in o.bus.log]
    assert sizes == sorted(sizes), "the whole transcript is carried forward"
    assert res.makespan_ms == res.work_ms, "strictly sequential"


def test_handoff_loses_the_task_when_the_baton_holder_dies():
    _, res, _, _, out, _ = orch(HandoffSwarm, task=TN, crash={"math-1": 1})
    assert res.status == "failed" and "baton lost" in res.detail and not out.success
    _, res, *_ = orch(HandoffSwarm, task=TN, crash={"math-1": 1}, redeliver=True)
    assert res.status == "failed", "a durable baton is useless without a replica to hand it to"
    _, res, _, _, out, _ = orch(HandoffSwarm, task=TN, crash={"math-1": 1}, redeliver=True, replicas={"math": 2})
    assert res.status == "final" and out.success and res.reassignments == 1


def test_handoff_recovery_duplicates_effects_unless_idempotent():
    kw = dict(task=TN, crash={"ops-1": 2}, redeliver=True, replicas={"ops": 2})
    assert orch(HandoffSwarm, **kw)[4].reason == "duplicate_effect"
    assert orch(HandoffSwarm, idempotent=True, **kw)[4].success


def test_orchestrators_tolerate_a_noisy_model_like_a_single_agent_does():
    noisy = ModelProfile(slip_rate=0.15, silent_fraction=0.0)
    for cls in (SupervisorWorkers, HandoffSwarm):
        _, res, _, _, out, _ = orch(cls, profile=noisy)
        assert res.status == "final" and out.success
