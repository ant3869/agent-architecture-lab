"""Model routing: static, role-based and cascade routers over a cheap and an expensive model.

Run:  python examples/12_model_routing.py
"""
from agentlab.core.runtime import Runtime
from agentlab.loops.verified_graph import VerifiedGraphLoop
from agentlab.routing.router import CascadeRouter, RoleRouter, RoutedModel, StaticRouter
from agentlab.sim.model import LARGE, SMALL, SimModel
from agentlab.sim.tasks import evaluate, make_suite
from agentlab.sim.world import World
from agentlab.tools.registry import StaticRegistry, world_tools

tasks = make_suite(60, stages=2, lookups=3, moved=1)
routers = {
    "all-small": lambda: StaticRouter("sim-small"),
    "all-large": lambda: StaticRouter("sim-large"),
    "role": lambda: RoleRouter("sim-large", "sim-small"),
    "cascade": lambda: CascadeRouter("sim-large", "sim-small"),
}
print(f"verified graph loop, {len(tasks)} tasks\n{'router':10} {'success':>8} {'cost/task':>10} {'large-model share':>18}")
for name, make in routers.items():
    ok = cost = large = calls = 0
    for task in tasks:
        world = World(task)
        model = RoutedModel({"sim-small": SimModel(SMALL, task, 5), "sim-large": SimModel(LARGE, task, 5)}, make())
        rt = Runtime(model, StaticRegistry(world_tools(world)), clock=world.clock)
        VerifiedGraphLoop(rt).run(task.goal_message())
        ok += evaluate(task, world).success
        cost += rt.meter.cost
        large += rt.meter.by_model.get("sim-large", 0)
        calls += rt.meter.model_calls
    print(f"{name:10} {ok / len(tasks):>8.0%} {cost / len(tasks):>10.2f} {large / calls:>18.0%}")
