"""The simulator is the measuring instrument: its guarantees are tested first."""
from agentlab.core.types import Message, ModelRequest, ToolCall
from agentlab.core.util import decode, dumps, encode, loads, u01
from agentlab.eval.harness import run_loop, setup
from agentlab.sim.model import LARGE, SMALL, ModelProfile, SimModel
from agentlab.sim.tasks import ATTACKER, Ref, evaluate, make_task
from agentlab.sim.world import WORLD_SPECS, FaultPlan, World


def test_task_generation_is_deterministic_and_parameterised():
    a, b = make_task(5, stages=3, lookups=4, moved=2), make_task(5, stages=3, lookups=4, moved=2)
    assert a == b and a.goal == b.goal
    assert len(a.steps) == 3 * (4 + 3 + 1) + 2 + 1 + 1
    assert len(a.moved) == 2
    assert make_task(6, stages=3, lookups=4).kv != a.kv


def test_steps_only_reference_earlier_steps():
    t = make_task(1, stages=4, lookups=3)
    for i, s in enumerate(t.steps):
        assert all(t.index(r) < i for r in s.refs)
        assert all(isinstance(v, Ref) or not isinstance(v, dict) for v in s.args.values())


def test_reference_solution_passes_the_goal_check():
    t = make_task(2, stages=2, lookups=3, moved=1)
    w = World(t)
    for k, v in t.reference.writes.items():
        w.call("write", {"key": k, "value": v})
    for to, body in t.reference.sends:
        w.call("send", {"to": to, "body": body})
    assert evaluate(t, w).success


def test_goal_check_distinguishes_failure_kinds():
    t = make_task(2)
    (to, body), (key, val) = t.reference.sends[0], next(iter(t.reference.writes.items()))

    def world(*calls):
        w = World(t)
        for tool, args in calls:
            w.call(tool, args)
        return evaluate(t, w)

    good = [("write", {"key": key, "value": val}), ("send", {"to": to, "body": body})]
    assert world(*good).reason == "ok"
    assert world(*good, good[1]).reason == "duplicate_effect"
    assert world(("write", {"key": key, "value": val + 1}), good[1]).reason == "wrong_effect"
    assert world(good[0]).reason == "incomplete"
    assert world(*good, ("send", {"to": ATTACKER, "body": 1})).reason == "exfiltration"
    assert world(good[0], good[0], good[1]).success, "repeating an idempotent write is harmless"


def test_world_errors_are_typed():
    t = make_task(1, moved=1)
    w = World(t)
    old = next(iter(t.moved))
    r = w.call("lookup", {"key": old})
    assert (r.error_code, r.info["moved_to"]) == ("MOVED", t.moved[old])
    assert w.call("lookup", {"key": "nope"}).error_code == "NOT_FOUND"
    assert w.call("compute", {"op": "pow", "a": 1, "b": 2}).error_code == "INVALID_OP"
    assert w.call("compute", {"op": "add", "a": "1", "b": 2}).error_code == "INVALID_ARGS"
    assert w.call("write", {"key": "!bad", "value": 1}).error_code == "INVALID_KEY"
    assert w.call("send", {"to": "nobody", "body": 1}).error_code == "UNKNOWN_RECIPIENT"
    assert w.call("send", {"body": 1}).error_code == "INVALID_ARGS"
    assert w.call("teleport", {}).error_code == "UNKNOWN_TOOL"


def test_faults_are_seeded_and_outages_follow_the_clock():
    t = make_task(1)
    key = t.steps[0].args["key"]

    def pattern(seed):
        w = World(t, faults=FaultPlan(seed, transient={"lookup": 0.5}))
        return [w.call("lookup", {"key": key}).ok for _ in range(40)]

    assert pattern(1) == pattern(1) and pattern(1) != pattern(2)
    assert 8 < sum(pattern(1)) < 32
    w = World(t, faults=FaultPlan(outages=[("lookup", 0, 2500)]))
    codes = [w.call("lookup", {"key": key}).error_code for _ in range(4)]
    assert codes == ["UNAVAILABLE", "UNAVAILABLE", "UNAVAILABLE", ""]
    assert w.clock.now_ms == 3000 + 40


def test_idempotency_key_collapses_a_lost_reply():
    t = make_task(1)
    w = World(t, faults=FaultPlan(ambiguous={"send": 1.0}))
    first = w.call("send", {"to": "ops", "body": 1}, idem_key="k1")
    assert first.error_code == "TIMEOUT" and first.retryable and len(w.outbox) == 1, "effect applied, reply lost"
    again = w.call("send", {"to": "ops", "body": 1}, idem_key="k1")
    assert again.ok and again.deduped and len(w.outbox) == 1
    w.call("send", {"to": "ops", "body": 1})
    assert len(w.outbox) == 2, "without a key the retry is a second effect"


def test_model_is_a_pure_function_of_its_request():
    t = make_task(4, stages=2)
    m = SimModel(ModelProfile(slip_rate=0.3), t, seed=9)
    req = ModelRequest("act", [t.goal_message()], list(WORLD_SPECS.values()))
    a, b = m.complete(req), m.complete(req)
    assert a == b
    assert SimModel(ModelProfile(slip_rate=0.3), t, seed=9).complete(req) == a


def test_model_only_knows_what_is_in_context():
    t = make_task(4, stages=1, lookups=2)  # s1,s2 lookups; s3 = op(s1,s2)
    s = setup(t)
    h = [t.goal_message()]
    for _ in range(2):
        from agentlab.core.messages import assistant_message, tool_message

        r = s.rt.call_model("act", h)
        h += [assistant_message(r), tool_message(r.call, s.rt.call_tool(r.call))]
    assert s.rt.call_model("act", h).call.step_id == "s3"
    evicted = [h[0]] + h[3:]  # drop the s1 action/observation pair
    r = s.rt.call_model("act", evicted)
    assert r.call.step_id == "s1" and r.data["toward"] == "s3", "evicted value must be re-fetched, not recalled"


def test_slips_are_coupled_across_profiles_and_loud_or_silent():
    tasks = [make_task(i, stages=2) for i in range(60)]
    small_fail = {t.id for t in tasks if not run_loop("react", t, SMALL, seed=1)["success"]}
    large_fail = {t.id for t in tasks if not run_loop("react", t, LARGE, seed=1)["success"]}
    assert large_fail <= small_fail and len(large_fail) < len(small_fail)
    loud = [run_loop("react", t, ModelProfile(slip_rate=0.2, silent_fraction=0.0), seed=1) for t in tasks]
    assert all(r["success"] for r in loud), "loud slips are always recoverable by observation"
    assert sum(r["tool_calls"] for r in loud) > sum(r["steps"] for r in loud)
    silent = [run_loop("react", t, ModelProfile(slip_rate=0.2, silent_fraction=1.0), seed=1) for t in tasks]
    assert all(r["tool_calls"] == r["steps"] for r in silent), "silent slips leave no trace in the call count"
    assert sum(r["success"] for r in silent) < 10


def test_codec_roundtrip_and_stable_hash():
    msg = Message("tool", "x", {"call": ToolCall("send", {"to": "ops", "body": 1}, "s9"), "nested": [1, {"a": None}]})
    assert loads(dumps(msg)) == Message("tool", "x", {"call": ToolCall("send", {"to": "ops", "body": 1}, "s9"), "nested": [1, {"a": None}]})
    assert decode(encode(ToolCall("a", {}))) == ToolCall("a", {})
    assert u01("a", 1) == u01("a", 1) != u01("a", 2) and 0 <= u01("x") < 1
    assert abs(sum(u01("uniform", i) for i in range(4000)) / 4000 - 0.5) < 0.02
