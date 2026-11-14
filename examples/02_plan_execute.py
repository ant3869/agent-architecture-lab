"""Plan-and-Execute: one planning call, symbolic references, replan only when a step fails.

Run:  python examples/02_plan_execute.py
"""
from agentlab.core.runtime import Runtime
from agentlab.loops.plan_execute import PlanExecuteLoop
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import StaticRegistry, world_tools

task = make_task(seed=7, stages=1, lookups=3, moved=1)
world = World(task)
rt = Runtime(SimModel(ModelProfile(), task), StaticRegistry(world_tools(world)), clock=world.clock)

result = PlanExecuteLoop(rt).run(task.goal_message())

for m in result.history:
    if m.role == "assistant" and "plan" in m.meta:
        print("--- plan ---")
        print(m.content)
    elif m.role == "tool":
        print("   ", m.content[:100])
print(f"\nstatus={result.status} replans={result.replans} model_calls={rt.meter.model_calls} (ReAct needs {len(task.steps) + 2}) tokens={rt.meter.total_tokens}")
print("goal check:", evaluate(task, world))
