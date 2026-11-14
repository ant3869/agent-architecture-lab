"""Tool registries: static (everything), scoped (capabilities + validation), lazy (search first).

Run:  python examples/08_tool_registries.py
"""
from agentlab.core.runtime import Runtime
from agentlab.core.types import ToolCall
from agentlab.core.util import estimate_tokens
from agentlab.loops.react import ReActLoop
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import LazyRegistry, ScopedRegistry, StaticRegistry, distractor_tools, world_tools

task = make_task(seed=1, stages=1, lookups=3)

for name, build in {
    "static": lambda cat: StaticRegistry(cat),
    "scoped": lambda cat: ScopedRegistry(cat, ["data", "math", "ops"]),
    "lazy": lambda cat: LazyRegistry(cat),
}.items():
    world = World(task)
    registry = build(world_tools(world) + distractor_tools(35))
    schema_tokens = sum(estimate_tokens(s.render()) for s in registry.specs())
    rt = Runtime(SimModel(ModelProfile(), task), registry, clock=world.clock)
    result = ReActLoop(rt).run(task.goal_message())
    print(f"{name:7} exposed at start: {schema_tokens:>5} schema tokens | prompt tokens for the task: {rt.meter.prompt_tokens:>6} | model calls: {rt.meter.model_calls} | {evaluate(task, world).reason}")

world = World(task)
scoped = ScopedRegistry(world_tools(world), ["math"])
print("\nscoped to 'math':", [s.name for s in scoped.specs()])
print("bad enum   ->", scoped.execute(ToolCall("compute", {"op": "pow", "a": 1, "b": 2})).error)
print("out of scope ->", scoped.execute(ToolCall("send", {"to": "ops", "body": 1})).error)
print("widening a scope is impossible:", [s.name for s in scoped.scope(["math", "ops"]).specs()])
