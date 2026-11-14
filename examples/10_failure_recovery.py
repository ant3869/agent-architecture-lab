"""Failure recovery: the same outage handled by the model, by backoff, and by a circuit breaker.

The primary `lookup` backend is down from t=2s to t=60s. A read replica exists.

Run:  python examples/10_failure_recovery.py
"""
from agentlab.core.runtime import Runtime
from agentlab.loops.react import ReActLoop
from agentlab.recovery.policies import CircuitBreakerTools, IdempotentTools, RetryingTools
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import FaultPlan, World
from agentlab.tools.registry import StaticRegistry, world_tools

task = make_task(seed=6, stages=2, lookups=3)


def run(label, build, faults):
    world = World(task, faults=faults)
    rt = Runtime(SimModel(ModelProfile(), task), build(world), clock=world.clock)
    result = ReActLoop(rt).run(task.goal_message())
    print(f"{label:28} {evaluate(task, world).reason:17} model_calls={rt.meter.model_calls:>3} backend_calls={len(world.calls):>3} time={world.clock.now_ms / 1000:>5.1f}s")


def base(world):
    return StaticRegistry(world_tools(world))


def breaker(world):
    full = StaticRegistry(world_tools(world, ("lookup", "lookup_replica", "compute", "write", "send")))
    return CircuitBreakerTools(RetryingTools(full, world.clock), world.clock, fallbacks={"lookup": "lookup_replica"})


outage = lambda: FaultPlan(outages=[("lookup", 2000, 60000)])
print("-- sustained outage of `lookup` --")
run("model-mediated retry", base, outage())
run("runtime backoff", lambda w: RetryingTools(base(w), w.clock), outage())
run("breaker + replica fallback", breaker, outage())

print("\n-- `send` succeeds but the response is lost (timeout) --")
lost_reply = lambda: FaultPlan(seed=1, ambiguous={"send": 0.6})
run("runtime backoff", lambda w: RetryingTools(base(w), w.clock), lost_reply())
run("backoff + idempotency keys", lambda w: IdempotentTools(RetryingTools(base(w), w.clock), task.id), lost_reply())
