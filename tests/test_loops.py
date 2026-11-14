import pytest

from agentlab.eval.harness import LOOPS, aggregate, metrics, run_loop, setup
from agentlab.loops.plan_execute import PlanExecuteLoop
from agentlab.loops.react import ReActLoop
from agentlab.loops.verified_graph import VerifiedGraphLoop
from agentlab.sim.model import ModelProfile
from agentlab.sim.tasks import make_suite, make_task

NOISY = ModelProfile(slip_rate=0.15, silent_fraction=0.5, verifier_miss_rate=0.0)


@pytest.mark.parametrize("loop", LOOPS)
@pytest.mark.parametrize("moved", [0, 2])
def test_every_loop_solves_tasks_with_a_perfect_model(loop, moved):
    for t in make_suite(15, stages=2, lookups=3, moved=moved):
        r = run_loop(loop, t)
        assert r["success"] and r["status"] == "final" and r["duplicate_effects"] == 0


def test_model_call_counts_match_each_loops_structure():
    t = make_task(1, stages=2, lookups=3)
    n = len(t.steps)
    assert run_loop("react", t)["model_calls"] == n + 1, "one call per step plus the final answer"
    assert run_loop("plan_execute", t)["model_calls"] == 2, "plan + finalize"
    effects = sum(1 for s in t.steps if s.tool in ("write", "send"))
    assert run_loop("verified_graph", t)["model_calls"] == 2 + effects, "plan + one gate per side effect + finalize"
    assert run_loop("verified_graph", t, loop_kwargs={"verify": "all"})["model_calls"] > 2 + effects


def test_plan_execute_replans_once_per_surprise_and_uses_fewer_tokens():
    t = make_task(1, stages=2, lookups=3, moved=2)
    pe, react = run_loop("plan_execute", t), run_loop("react", t)
    assert pe["replans"] == 2 and pe["model_calls"] == 4
    assert react["model_calls"] == len(t.steps) + 1 + 2
    assert pe["total_tokens"] < react["total_tokens"]


def test_react_and_plan_execute_fail_on_exactly_the_same_tasks():
    """Paired noise: neither loop can see a silent error, so their outcomes coincide."""
    tasks = make_suite(80, stages=2, lookups=3)
    a = [run_loop("react", t, NOISY, seed=2)["success"] for t in tasks]
    b = [run_loop("plan_execute", t, NOISY, seed=2)["success"] for t in tasks]
    assert a == b and 0 < sum(a) < len(a)


def test_verified_graph_with_a_perfect_verifier_never_commits_a_wrong_effect():
    tasks = make_suite(80, stages=2, lookups=3, moved=1)
    rows = [run_loop("verified_graph", t, NOISY, seed=2) for t in tasks]
    assert all(r["success"] for r in rows)
    assert all(r["wrong_effects"] == 0 and r["duplicate_effects"] == 0 for r in rows)
    assert sum(r["repairs"] for r in rows) > 0, "the scenario must actually exercise repair"
    react = aggregate(run_loop("react", t, NOISY, seed=2) for t in tasks)
    assert react["success_rate"] < 0.6


def test_verified_graph_gates_every_side_effect_behind_verify():
    t = make_task(3, stages=2, lookups=2)
    s = setup(t, NOISY, seed=5, trace=True)
    loop = VerifiedGraphLoop(s.rt)
    loop.run(t.goal_message())
    kinds = [(e["kind"], e["data"]) for e in s.tracer.events]
    last_verify_ok = False
    for kind, d in kinds:
        if kind == "model_call" and d["mode"] == "verify":
            last_verify_ok = d["response"]["text"] == "VERIFY: ok"
        elif kind == "model_call":
            last_verify_ok = False
        elif kind == "tool_result" and d["call"]["tool"] in ("write", "send"):
            assert last_verify_ok, "side effect executed without an immediately preceding successful verification"
            last_verify_ok = False
    assert ("verify", "execute") in loop.transitions


def test_imperfect_verifier_degrades_gracefully_not_catastrophically():
    tasks = make_suite(80, stages=2, lookups=3)
    rate = lambda miss: aggregate(run_loop("verified_graph", t, ModelProfile(slip_rate=0.15, verifier_miss_rate=miss), seed=2) for t in tasks)["success_rate"]
    assert rate(0.0) == 1.0 > rate(0.3) > rate(1.0)
    react = aggregate(run_loop("react", t, ModelProfile(slip_rate=0.15), seed=2) for t in tasks)["success_rate"]
    assert rate(1.0) == react, "a verifier that sees nothing reduces the graph to an unverified loop"


def test_loops_terminate_under_their_budgets():
    t = make_task(1, stages=2)
    hopeless = ModelProfile(slip_rate=1.0, silent_fraction=0.0)  # every call is malformed
    s = setup(t, hopeless)
    assert ReActLoop(s.rt, max_iters=7).run(t.goal_message()).status == "max_iters" and s.meter.tool_calls == 7
    s = setup(t, hopeless)
    r = PlanExecuteLoop(s.rt, max_replans=3).run(t.goal_message())
    assert r.status == "failed" and r.replans == 3
    s = setup(t, hopeless)
    r = VerifiedGraphLoop(s.rt, max_replans=3).run(t.goal_message())
    assert r.status == "failed" and "budget" in r.detail
    assert not metrics(s, r)["success"]


def test_metrics_schema_is_shared_by_all_loops():
    t = make_task(1)
    keys = [set(run_loop(name, t)) for name in LOOPS]
    assert keys[0] == keys[1] == keys[2] and {"success", "total_tokens", "peak_context", "sim_ms"} <= keys[0]
