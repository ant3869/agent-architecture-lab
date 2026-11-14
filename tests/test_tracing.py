import pytest

from agentlab.core.runtime import Runtime
from agentlab.core.trace import ReplayDivergence, ReplayModel, ReplayTools, Tape, Tracer, build_spans, read_jsonl
from agentlab.core.util import SimClock
from agentlab.eval.harness import LOOPS, setup
from agentlab.loops.plan_execute import PlanExecuteLoop
from agentlab.loops.react import ReActLoop
from agentlab.sim.model import ModelProfile
from agentlab.sim.tasks import make_task

T = make_task(8, stages=2, lookups=2, moved=1)
NOISY = ModelProfile(slip_rate=0.2)


def record(loop="react"):
    s = setup(T, NOISY, seed=2, trace=True)
    LOOPS[loop](s.rt).run(T.goal_message())
    return s


def test_event_log_is_ordered_complete_and_roundtrips(tmp_path):
    s = record()
    ev = s.tracer.events
    assert [e["seq"] for e in ev] == list(range(len(ev)))
    assert [e["t_ms"] for e in ev] == sorted(e["t_ms"] for e in ev)
    assert sum(e["kind"] == "model_call" for e in ev) == s.meter.model_calls
    assert sum(e["kind"] == "tool_result" for e in ev) == s.meter.tool_calls
    s.tracer.write_jsonl(tmp_path / "t.jsonl")
    assert read_jsonl(tmp_path / "t.jsonl") == ev


def test_disabled_tracer_records_nothing():
    s = setup(T)
    ReActLoop(s.rt).run(T.goal_message())
    assert s.tracer.events == []


def test_span_tree_structure_and_attributes():
    s = record()
    spans = build_spans(s.tracer.events)
    root = spans[0]
    assert root["name"] == "react.run" and root["parent_span_id"] == "" and root["status"] == "ok"
    leaves = spans[1:]
    assert all(l["parent_span_id"] == root["span_id"] for l in leaves)
    assert all(root["start_ms"] <= l["start_ms"] <= l["end_ms"] <= root["end_ms"] for l in leaves)
    chats = [l for l in leaves if l["attributes"]["gen_ai.operation.name"] == "chat"]
    tools = [l for l in leaves if l["attributes"]["gen_ai.operation.name"] == "execute_tool"]
    assert sum(c["attributes"]["gen_ai.usage.input_tokens"] for c in chats) == s.meter.prompt_tokens
    assert sum(c["end_ms"] - c["start_ms"] for c in chats) + sum(t["end_ms"] - t["start_ms"] for t in tools) == s.clock.now_ms
    failed = [t for t in tools if t["status"] == "error"]
    assert failed and all("error.type" in t["attributes"] for t in failed)


def test_span_records_failure_status():
    tr = Tracer()
    with pytest.raises(RuntimeError):
        with tr.span("outer"):
            with tr.span("inner"):
                raise RuntimeError("boom")
    spans = build_spans(tr.events)
    assert [(s["name"], s["status"], s["parent_span_id"]) for s in spans] == [("outer", "RuntimeError", ""), ("inner", "RuntimeError", "sp1")]


@pytest.mark.parametrize("loop", LOOPS)
def test_replay_reproduces_the_exact_event_stream_without_model_or_world(loop):
    s = record(loop)
    tape = Tape(s.tracer.events)
    clock = SimClock()
    tracer = Tracer(clock)
    rt = Runtime(ReplayModel(tape), ReplayTools(tape, s.tools.specs(), clock), clock=clock, tracer=tracer)
    result = LOOPS[loop](rt).run(T.goal_message())
    assert result.status == "final" and tracer.events == s.tracer.events


def test_replay_detects_divergence():
    s = record()
    tape = Tape(s.tracer.events)
    rt = Runtime(ReplayModel(tape), ReplayTools(tape, s.tools.specs()))
    with pytest.raises(ReplayDivergence, match="differs"):
        PlanExecuteLoop(rt).run(T.goal_message())
    short = Tape(s.tracer.events[:6])
    rt = Runtime(ReplayModel(short), ReplayTools(short, s.tools.specs()))
    with pytest.raises(ReplayDivergence, match="more times than recorded"):
        ReActLoop(rt).run(T.goal_message())
