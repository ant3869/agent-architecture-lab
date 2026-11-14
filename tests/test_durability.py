import pytest

from agentlab.core.runtime import Meter, Runtime
from agentlab.core.types import SimulatedCrash
from agentlab.durability.crash import STRATEGIES, CrashingTools, CrashSchedule, run_with_crashes
from agentlab.durability.journal import DurableSession, NonDeterminismError
from agentlab.durability.stores import SQLiteCheckpointer, SQLiteJournal
from agentlab.loops.plan_execute import PlanExecuteLoop
from agentlab.loops.react import ReActLoop
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import StaticRegistry, world_tools

TASK = make_task(2, stages=2, lookups=2, notify_stages=True)
N = len(TASK.steps)
SENDS = [i + 1 for i, s in enumerate(TASK.steps) if s.tool == "send"]
POINTS = [(k, phase) for k in range(1, N + 1) for phase in ("before", "after")]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_no_crash_baseline_is_correct(strategy):
    r = run_with_crashes(strategy, TASK)
    assert r["success"] and r["restarts"] == 0 and r["backend_calls"] == N


@pytest.mark.parametrize("strategy", ["snapshot+idem", "graph_checkpoint+idem", "journal+idem"])
def test_persistence_plus_idempotency_survives_every_single_crash_point(strategy):
    for point in POINTS:
        r = run_with_crashes(strategy, TASK, crashes=[point])
        assert r["success"] and r["duplicate_effects"] == 0 and r["restarts"] == 1, point


@pytest.mark.parametrize("strategy", ["snapshot", "graph_checkpoint", "journal"])
def test_without_idempotency_the_only_failures_are_crashes_right_after_a_send(strategy):
    failed = [p for p in POINTS if not run_with_crashes(strategy, TASK, crashes=[p])["success"]]
    assert failed == [(k, "after") for k in SENDS]


def test_restart_from_scratch_repeats_every_earlier_send():
    r = run_with_crashes("restart", TASK, crashes=[(N, "before")])
    assert not r["success"] and r["duplicate_effects"] == len(SENDS) - 1
    assert r["model_calls"] > run_with_crashes("journal", TASK, crashes=[(N, "before")])["model_calls"]


def test_journal_recovery_reissues_no_model_calls():
    base = run_with_crashes("journal+idem", TASK)["model_calls"]
    for point in POINTS[::3]:
        assert run_with_crashes("journal+idem", TASK, crashes=[point])["model_calls"] == base
    snap = run_with_crashes("snapshot+idem", TASK, crashes=[(4, "after")])
    assert snap["model_calls"] == base + 1, "a snapshot loses the in-flight iteration and re-asks the model once"


def test_three_crashes_in_one_run():
    for strategy in ("snapshot+idem", "journal+idem", "graph_checkpoint+idem"):
        r = run_with_crashes(strategy, TASK, crashes=[(3, "after"), (SENDS[0], "after"), (N, "after")])
        assert r["success"] and r["restarts"] == 3 and r["duplicate_effects"] == 0


def test_journal_and_checkpoints_survive_on_disk(tmp_path):
    path = str(tmp_path / "state.sqlite")
    world = World(TASK)
    schedule = CrashSchedule([(5, "after")])

    def process():
        journal = SQLiteJournal(path)
        session = DurableSession(journal, TASK.id)
        tools = session.tools(CrashingTools(StaticRegistry(world_tools(world)), schedule))
        meter = Meter()
        rt = Runtime(session.model(SimModel(ModelProfile(), TASK)), tools, clock=world.clock, meter=meter)
        try:
            return ReActLoop(rt).run(TASK.goal_message()), meter
        finally:
            journal.close()

    with pytest.raises(SimulatedCrash):
        process()
    result, meter = process()
    assert result.status == "final" and evaluate(TASK, world).success
    assert meter.replayed_model_calls == 5 and meter.replayed_tool_calls == 4
    cp = SQLiteCheckpointer(str(tmp_path / "cp.sqlite"))
    cp.put("t", {"history": [TASK.goal_message()]})
    cp.close()
    assert SQLiteCheckpointer(str(tmp_path / "cp.sqlite")).latest("t")["history"][0] == TASK.goal_message()


def test_replaying_different_code_against_a_journal_is_detected():
    world, journal = World(TASK), SQLiteJournal()

    def runtime():
        s = DurableSession(journal, "run")
        return Runtime(s.model(SimModel(ModelProfile(), TASK)), s.tools(StaticRegistry(world_tools(world))), clock=world.clock)

    ReActLoop(runtime()).run(TASK.goal_message())
    with pytest.raises(NonDeterminismError):
        PlanExecuteLoop(runtime()).run(TASK.goal_message())


def test_journal_is_smaller_than_snapshots():
    j, s = run_with_crashes("journal", TASK), run_with_crashes("snapshot", TASK)
    assert j["store_bytes"] < s["store_bytes"] / 2


def test_crash_schedule_validates_phase():
    with pytest.raises(ValueError):
        CrashSchedule([(1, "during")])
    with pytest.raises(ValueError):
        run_with_crashes("hope", TASK)
