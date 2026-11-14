import pytest

from agentlab.core.runtime import Runtime
from agentlab.core.types import Message
from agentlab.eval.harness import run_loop, setup
from agentlab.memory.context import Compaction, FactLedger, FullHistory, SlidingWindow, tokens
from agentlab.sim.tasks import make_task

LONG = make_task(4, stages=6, lookups=3)


def run(policy, task=LONG):
    return run_loop("react", task, loop_kwargs={"memory": policy, "max_iters": 4 * len(task.steps)})


def test_full_history_is_the_identity_and_grows_quadratically():
    short = make_task(4, stages=2, lookups=3)
    a, b = run(FullHistory(), short), run(FullHistory())
    assert b["steps"] / a["steps"] < 3 and b["total_tokens"] / a["total_tokens"] > 5


def test_sliding_window_pins_the_goal_and_bounds_the_view():
    h = [Message("user", "goal")] + [Message("tool", f"m{i}") for i in range(20)]
    v = SlidingWindow(4).view(h, None)
    assert [m.content for m in v] == ["goal", "m16", "m17", "m18", "m19"]
    assert SlidingWindow(40).view(h, None) is h
    with pytest.raises(ValueError):
        SlidingWindow(1)


def test_small_window_livelocks_and_larger_window_pays_in_refetches():
    tiny = run(SlidingWindow(6))
    assert tiny["status"] == "max_iters" and not tiny["success"] and tiny["duplicate_effects"] == 0
    ok, full = run(SlidingWindow(16)), run(FullHistory())
    assert ok["success"] and ok["tool_calls"] > full["tool_calls"] and ok["peak_context"] < full["peak_context"]


def test_compaction_bounds_context_and_keeps_the_task_solvable():
    policy = Compaction(max_tokens=500, keep_recent=4)
    r, full = run(policy), run(FullHistory())
    assert r["success"] and r["tool_calls"] == full["tool_calls"], "nothing had to be re-fetched"
    assert policy.compactions >= 2 and r["model_calls"] == full["model_calls"] + policy.compactions
    assert r["peak_context"] < full["peak_context"] and r["total_tokens"] < full["total_tokens"]


def test_compaction_summary_carries_facts_relocations_and_retry_counts():
    t = make_task(2, stages=2, lookups=3, moved=2)
    s = setup(t)
    from agentlab.loops.react import ReActLoop

    policy = Compaction(max_tokens=150, keep_recent=2)
    result = ReActLoop(s.rt, memory=policy).run(t.goal_message())
    view = policy.view(result.history, s.rt)
    assert view[0] is result.history[0] and view[1].role == "memory"
    assert set(view[1].meta["moved"]) == set(t.moved)
    assert view[1].meta["facts"]["s1"] == t.reference.outputs["s1"]
    assert tokens(view) < tokens(result.history) / 2


def test_fact_ledger_needs_no_model_calls_and_is_cheapest():
    ledger, full, compact = run(FactLedger()), run(FullHistory()), run(Compaction(500))
    assert ledger["success"] and ledger["model_calls"] == full["model_calls"]
    assert ledger["total_tokens"] < compact["total_tokens"] < full["total_tokens"]


def test_ledger_tracks_relocations_and_invalidations():
    t = make_task(2, stages=1, lookups=3, moved=1)
    assert run(FactLedger(), t)["success"]
    led = FactLedger()
    h = [t.goal_message(), Message("tool", "x", {"step_id": "s1", "ok": True, "output": 5, "tool": "lookup", "args": {}, "error_code": "", "info": {}}), Message("system", "v", {"invalid": ["s1"]}), Message("assistant", "a"), Message("tool", "b", {})]
    view = led.view(h, None)
    assert view[1].meta["facts"] == {} and view[1].meta["done"] == []
