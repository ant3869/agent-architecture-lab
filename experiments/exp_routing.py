"""E6 - model routing: static, role-based and cascade."""
from __future__ import annotations

from agentlab.eval.harness import run_loop
from agentlab.routing.router import CascadeRouter, RoleRouter, RoutedModel, StaticRouter
from agentlab.sim.model import LARGE, SMALL, SimModel
from agentlab.sim.tasks import Task, make_suite

from .common import cell, experiment, find, pct

ROUTERS = {
    "all-small": lambda: StaticRouter("sim-small"),
    "all-large": lambda: StaticRouter("sim-large"),
    "role (plan/verify large)": lambda: RoleRouter("sim-large", "sim-small"),
    "cascade (escalate on failure)": lambda: CascadeRouter("sim-large", "sim-small"),
    "cascade, small verifier": lambda: CascadeRouter("sim-large", "sim-small", strong_modes=()),
}


def one(loop: str, router_factory, task: Task) -> dict:
    models = {"sim-small": SimModel(SMALL, task, 5), "sim-large": SimModel(LARGE, task, 5)}
    row = run_loop(loop, task, model=RoutedModel(models, router_factory()))
    return row


def run(n: int = 200) -> dict:
    tasks = make_suite(n, stages=2, lookups=3, moved=1)
    rows = []
    for loop in ("react", "plan_execute", "verified_graph"):
        for name, mk in ROUTERS.items():
            rows.append(cell({"scenario": loop, "arch": name}, [one(loop, mk, t) for t in tasks]))
    r = lambda sc, a: find(rows, scenario=sc, arch=a)
    vg = "verified_graph"
    findings = [
        f"ReAct: all-large succeeds {r('react','all-large')['success_rate']:.0%} at cost {r('react','all-large')['cost_mean']:.1f}; all-small {r('react','all-small')['success_rate']:.0%} at {r('react','all-small')['cost_mean']:.1f}. "
        f"The cascade reaches only {r('react','cascade (escalate on failure)')['success_rate']:.0%}: it escalates on loud errors but silent errors give it no signal.",
        f"Verified graph: the cascade reaches {r(vg,'cascade (escalate on failure)')['success_rate']:.0%} at cost {r(vg,'cascade (escalate on failure)')['cost_mean']:.1f} versus all-large {r(vg,'all-large')['success_rate']:.0%} at {r(vg,'all-large')['cost_mean']:.1f} "
        f"({pct(r(vg,'cascade (escalate on failure)')['cost_mean'], r(vg,'all-large')['cost_mean'])} cost).",
        f"Keeping the verifier on the small model too ('cascade, small verifier') costs {r(vg,'cascade, small verifier')['cost_mean']:.1f} and reaches {r(vg,'cascade, small verifier')['success_rate']:.0%}: "
        f"most of the routed cost is the strong verifier re-reading the transcript, and most of the reliability comes from it.",
        f"Role routing on the verified graph: {r(vg,'role (plan/verify large)')['success_rate']:.0%} at cost {r(vg,'role (plan/verify large)')['cost_mean']:.1f}. On ReAct it equals all-small because every ReAct call has the same role.",
        f"Configurations above 90% success, cheapest first: "
        + "; ".join(f"{x['scenario']}/{x['arch']} ({x['success_rate']:.0%}, {x['cost_mean']:.1f})" for x in sorted((x for x in rows if x["success_rate"] >= 0.9), key=lambda x: x["cost_mean"])[:3]) + ".",
    ]
    return experiment(
        "routing",
        "Model selection and cost",
        "Can a router buy large-model reliability at small-model prices, and what does it need to work?",
        {"tasks_per_cell": n, "sim-small": {"slip_rate": SMALL.slip_rate, "verifier_miss_rate": SMALL.verifier_miss_rate, "cost_in": SMALL.cost_in, "cost_out": SMALL.cost_out},
         "sim-large": {"slip_rate": LARGE.slip_rate, "verifier_miss_rate": LARGE.verifier_miss_rate, "cost_in": LARGE.cost_in, "cost_out": LARGE.cost_out}, "cost_unit": "abstract units per 1k tokens (12x price ratio)"},
        [("arch", "Router"), ("success_rate", "Success"), ("cost_mean", "Cost"), ("model_calls_mean", "Model calls"), ("total_tokens_mean", "Tokens"), ("repairs_mean", "Repairs")],
        ["scenario"],
        rows,
        findings,
        [
            "Prices and error rates are assumptions chosen for a 12x price ratio; they are not measurements of any real model.",
            "The large model's slips are a strict subset of the small model's (coupled draws). Real models fail on different inputs.",
            "No learned router is evaluated; RouteLLM-style routers need preference data this simulator cannot provide.",
        ],
    )
