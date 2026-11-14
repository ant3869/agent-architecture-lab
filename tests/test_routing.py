from agentlab.core.types import Message, ModelRequest
from agentlab.eval.harness import aggregate, run_loop
from agentlab.routing.router import CascadeRouter, RoleRouter, RoutedModel, StaticRouter
from agentlab.sim.model import LARGE, SMALL, SimModel
from agentlab.sim.tasks import make_suite

TASKS = make_suite(60, stages=2, lookups=3, moved=1)


def routed(loop, router_factory):
    rows = []
    for t in TASKS:
        model = RoutedModel({"sim-small": SimModel(SMALL, t, 5), "sim-large": SimModel(LARGE, t, 5)}, router_factory())
        rows.append(run_loop(loop, t, model=model))
    return aggregate(rows)


def req(mode, last=None):
    return ModelRequest(mode, [Message("user", "g")] + ([last] if last else []), [])


def test_router_decisions():
    role = RoleRouter("L", "S")
    assert [role.choose(req(m)) for m in ("plan", "act", "verify", "finalize")] == ["L", "S", "L", "S"]
    c = CascadeRouter("L", "S")
    assert c.choose(req("act")) == "S"
    assert c.choose(req("act", Message("tool", "ok", {"ok": True}))) == "S"
    assert c.choose(req("act", Message("tool", "err", {"ok": False}))) == "L"
    assert c.choose(req("replan", Message("system", "v", {"invalid": ["s1"]}))) == "L"
    assert c.choose(req("verify")) == "L" and c.escalations == 2
    assert StaticRouter("X").choose(req("act")) == "X"


def test_static_routing_brackets_cost_and_quality():
    small, large = routed("react", lambda: StaticRouter("sim-small")), routed("react", lambda: StaticRouter("sim-large"))
    assert small["success_rate"] < large["success_rate"] and small["cost_mean"] * 5 < large["cost_mean"]


def test_role_routing_is_a_noop_for_single_role_loops():
    assert routed("react", lambda: RoleRouter("sim-large", "sim-small")) == routed("react", lambda: StaticRouter("sim-small"))


def test_cascade_without_a_failure_detector_cannot_fix_silent_errors():
    small, cascade = routed("react", lambda: StaticRouter("sim-small")), routed("react", lambda: CascadeRouter("sim-large", "sim-small"))
    assert abs(cascade["success_rate"] - small["success_rate"]) < 0.1


def test_cascade_with_verification_approaches_large_model_quality_for_less():
    large = routed("verified_graph", lambda: StaticRouter("sim-large"))
    cascade = routed("verified_graph", lambda: CascadeRouter("sim-large", "sim-small"))
    small = routed("verified_graph", lambda: StaticRouter("sim-small"))
    assert cascade["success_rate"] >= large["success_rate"] - 0.08 and cascade["success_rate"] > small["success_rate"]
    assert small["cost_mean"] < cascade["cost_mean"] < large["cost_mean"]
