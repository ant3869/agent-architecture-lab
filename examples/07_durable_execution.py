"""Durable execution: crash an agent mid-task twice, recover from an on-disk journal.

The journal is a real SQLite file. Each "process" below builds everything from
scratch and shares only that file and the external world.

Run:  python examples/07_durable_execution.py
"""
import tempfile
from pathlib import Path

from agentlab.core.runtime import Meter, Runtime
from agentlab.core.types import SimulatedCrash
from agentlab.durability.crash import CrashingTools, CrashSchedule
from agentlab.durability.journal import DurableSession
from agentlab.durability.stores import SQLiteJournal
from agentlab.loops.react import ReActLoop
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import StaticRegistry, world_tools

task = make_task(seed=2, stages=2, lookups=2, notify_stages=True)
world = World(task)  # the outside world survives agent crashes
crashes = CrashSchedule([(6, "after"), (11, "after")])  # both land right after a non-idempotent send
db = Path(tempfile.mkdtemp()) / "journal.sqlite"

for process in range(1, 10):
    journal = SQLiteJournal(str(db))  # reopened from disk by every process
    session = DurableSession(journal, run_id=task.id)
    meter = Meter()
    tools = session.tools(CrashingTools(StaticRegistry(world_tools(world)), crashes))
    rt = Runtime(session.model(SimModel(ModelProfile(), task)), tools, clock=world.clock, meter=meter)
    try:
        result = ReActLoop(rt).run(task.goal_message())
    except SimulatedCrash as crash:
        print(f"process {process}: {crash}  (live model calls={meter.model_calls}, replayed={meter.replayed_model_calls})")
        journal.close()
        continue
    print(f"process {process}: finished status={result.status} (live model calls={meter.model_calls}, replayed from journal={meter.replayed_model_calls})")
    break

outcome = evaluate(task, world)
print(f"\nsends delivered: {world.outbox}")
print(f"goal check: {outcome.reason}, duplicate effects: {outcome.duplicate_effects}, deduped by idempotency key: {sum(1 for c in world.calls if c['deduped'])}")
