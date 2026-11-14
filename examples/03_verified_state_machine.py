"""Verified graph loop: an explicit state machine that verifies before every side effect.

The model here slips 25% of the time and half of those slips are silent (a valid call
with the wrong meaning). Watch the verify -> repair transitions catch them.

Run:  python examples/03_verified_state_machine.py
"""
from agentlab.core.runtime import Runtime
from agentlab.loops.react import ReActLoop
from agentlab.loops.verified_graph import VerifiedGraphLoop
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import StaticRegistry, world_tools

profile = ModelProfile(slip_rate=0.25, silent_fraction=0.5, verifier_miss_rate=0.0)
task = make_task(seed=3, stages=2, lookups=2)


def run(loop_cls):
    world = World(task)
    rt = Runtime(SimModel(profile, task, seed=1), StaticRegistry(world_tools(world)), clock=world.clock)
    loop = loop_cls(rt)
    result = loop.run(task.goal_message())
    return loop, result, rt, evaluate(task, world)


loop, result, rt, outcome = run(VerifiedGraphLoop)
print("transitions:", " -> ".join([loop.transitions[0][0]] + [dst for _, dst in loop.transitions]))
print(f"verified graph: status={result.status} repairs={result.repairs} replans={result.replans} model_calls={rt.meter.model_calls} -> {outcome.reason}")

_, result, rt, outcome = run(ReActLoop)
print(f"react (same model, same slips): status={result.status} model_calls={rt.meter.model_calls} -> {outcome.reason}")
