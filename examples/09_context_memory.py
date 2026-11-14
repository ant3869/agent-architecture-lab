"""Context management on a 57-step task: full history, sliding windows, compaction, fact ledger.

Run:  python examples/09_context_memory.py
"""
from agentlab.core.runtime import Runtime
from agentlab.loops.react import ReActLoop
from agentlab.memory.context import Compaction, FactLedger, FullHistory, SlidingWindow
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import StaticRegistry, world_tools

task = make_task(seed=4, stages=8, lookups=3)
print(f"{len(task.steps)}-step task\n{'policy':16} {'result':11} {'tokens':>8} {'peak ctx':>9} {'model calls':>12} {'tool calls':>11}")
for policy in (FullHistory(), SlidingWindow(6), SlidingWindow(16), Compaction(600), FactLedger()):
    world = World(task)
    rt = Runtime(SimModel(ModelProfile(), task), StaticRegistry(world_tools(world)), clock=world.clock)
    result = ReActLoop(rt, memory=policy, max_iters=4 * len(task.steps)).run(task.goal_message())
    outcome = evaluate(task, world)
    label = outcome.reason if result.status == "final" else result.status
    print(f"{policy.name:16} {label:11} {rt.meter.total_tokens:>8} {rt.meter.peak_prompt_tokens:>9} {rt.meter.model_calls:>12} {rt.meter.tool_calls:>11}")
