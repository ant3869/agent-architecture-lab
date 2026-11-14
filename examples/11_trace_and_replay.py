"""Execution logging and replay: record a run, export spans, replay it with no model and no world.

Run:  python examples/11_trace_and_replay.py
"""
import tempfile
from pathlib import Path

from agentlab.core.runtime import Runtime
from agentlab.core.trace import ReplayDivergence, ReplayModel, ReplayTools, Tape, Tracer, build_spans, read_jsonl
from agentlab.core.util import SimClock
from agentlab.loops.plan_execute import PlanExecuteLoop
from agentlab.loops.react import ReActLoop
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import make_task
from agentlab.sim.world import World
from agentlab.tools.registry import StaticRegistry, world_tools

task = make_task(seed=8, stages=1, lookups=3, moved=1)
world = World(task)
tracer = Tracer(world.clock)
tools = StaticRegistry(world_tools(world))
ReActLoop(Runtime(SimModel(ModelProfile(slip_rate=0.2), task, seed=2), tools, clock=world.clock, tracer=tracer)).run(task.goal_message())

path = Path(tempfile.mkdtemp()) / "run.jsonl"
tracer.write_jsonl(path)
events = read_jsonl(path)
print(f"1. event log: {len(events)} events, {path.stat().st_size} bytes -> {path}")

spans = build_spans(events)
print(f"2. span tree: {len(spans)} spans")
for s in spans[:6]:
    print(f"   {'  ' if s['parent_span_id'] else ''}{s['name']:24} {s['start_ms']:>6}-{s['end_ms']:<6}ms {s['status']:6} {s['attributes'].get('gen_ai.usage.input_tokens', '')}")

tape = Tape(events)
clock = SimClock()
replay_tracer = Tracer(clock)
rt = Runtime(ReplayModel(tape), ReplayTools(tape, tools.specs(), clock), clock=clock, tracer=replay_tracer)
ReActLoop(rt).run(task.goal_message())
print(f"3. replay: identical event stream = {replay_tracer.events == events}, world calls made during replay = 0")

try:  # replaying different code against the same tape is detected, not silently accepted
    clock = SimClock()
    PlanExecuteLoop(Runtime(ReplayModel(tape), ReplayTools(tape, tools.specs(), clock), clock=clock)).run(task.goal_message())
except ReplayDivergence as e:
    print(f"4. replaying a different loop against the tape -> ReplayDivergence: {e}")
