"""Single-agent ReAct loop: one model call per tool call, observation fed back each time.

Run:  python examples/01_react_loop.py
"""
from agentlab.core.runtime import Runtime
from agentlab.loops.react import ReActLoop
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import StaticRegistry, world_tools

task = make_task(seed=7, stages=1, lookups=3, moved=1)  # one key has been relocated: a surprise
world = World(task)
rt = Runtime(SimModel(ModelProfile(), task), StaticRegistry(world_tools(world)), clock=world.clock)

result = ReActLoop(rt).run(task.goal_message())

for m in result.history:
    print(f"[{m.role:9}] {m.content.splitlines()[-1][:110]}")
print(f"\nstatus={result.status} iterations={result.iterations} model_calls={rt.meter.model_calls} tokens={rt.meter.total_tokens}")
print("goal check:", evaluate(task, world))
