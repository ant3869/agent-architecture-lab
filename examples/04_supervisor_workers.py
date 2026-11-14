"""Supervisor-worker orchestration with parallel specialist workers and a worker crash.

Run:  python examples/04_supervisor_workers.py
"""
from agentlab.core.runtime import Meter
from agentlab.core.util import SimClock
from agentlab.orchestration.supervisor import SupervisorWorkers
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import world_tools

task = make_task(seed=5, stages=3, lookups=3)
clock = SimClock()
world, meter = World(task, clock), Meter()

sup = SupervisorWorkers(
    SimModel(ModelProfile(), task),
    world_tools(world),
    clock=clock,
    meter=meter,
    pool={"data": 2, "math": 2, "ops": 1},  # workers per skill
    crash={"data-1": 2},  # data-1 dies right after its 2nd tool call
    idempotent=True,
)
res = sup.run(task)

print(f"{'subtask':10} {'worker':8} {'start':>6} {'end':>6}  state")
for row in res.timeline:
    print(f"{row['subtask']:10} {row['worker']:8} {row['start']:>6} {row['end']:>6}  {row['state']}")
print(f"\nstatus={res.status} makespan={res.makespan_ms}ms total_work={res.work_ms}ms reassignments={res.reassignments}")
print(f"messages={res.messages} model_calls={meter.model_calls} tokens={meter.total_tokens} peak_context={meter.peak_prompt_tokens}")
print("goal check:", evaluate(task, world))
