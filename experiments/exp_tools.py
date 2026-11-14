"""E7 - tool registries under a 40-tool catalogue."""
from __future__ import annotations

from agentlab.eval.harness import run_loop
from agentlab.sim.model import ModelProfile
from agentlab.sim.tasks import make_suite
from agentlab.tools.registry import LazyRegistry, ScopedRegistry, StaticRegistry, distractor_tools, world_tools

from .common import cell, experiment, find, pct

EXTRA = ("exposed_tools", "backend_errors", "rejected_pre_execution")


def one(kind: str, task, profile) -> dict:
    holder = {}

    def wrap(tools, world):
        catalogue = world_tools(world) + distractor_tools(35)
        reg = {"static": lambda: StaticRegistry(catalogue), "scoped": lambda: ScopedRegistry(catalogue, ["data", "math", "ops"]), "lazy": lambda: LazyRegistry(catalogue)}[kind]()
        holder["reg"], holder["world"] = reg, world
        return reg

    row = run_loop("react", task, profile, seed=3, wrap=wrap)
    row["exposed_tools"] = len(holder["reg"].specs())
    row["backend_errors"] = sum(1 for c in holder["world"].calls if not c["ok"])
    row["rejected_pre_execution"] = getattr(holder["reg"], "rejected", 0)
    return row


def run(n: int = 200) -> dict:
    tasks = make_suite(max(10, n // 2), stages=2, lookups=3)
    rows = []
    for sc, profile in (("perfect model", ModelProfile()), ("loud slips 10%", ModelProfile(slip_rate=0.10, silent_fraction=0.0))):
        for kind in ("static", "scoped", "lazy"):
            rows.append(cell({"scenario": sc, "arch": kind}, [one(kind, t, profile) for t in tasks], EXTRA))
    r = lambda sc, a: find(rows, scenario=sc, arch=a)
    p = "perfect model"
    findings = [
        f"Exposing all 40 schemas on every call costs {r(p,'static')['prompt_tokens_mean']:.0f} prompt tokens per task; scoping to the task's three capability domains costs {r(p,'scoped')['prompt_tokens_mean']:.0f} "
        f"({pct(r(p,'scoped')['prompt_tokens_mean'], r(p,'static')['prompt_tokens_mean'])}); lazy discovery costs {r(p,'lazy')['prompt_tokens_mean']:.0f} ({pct(r(p,'lazy')['prompt_tokens_mean'], r(p,'static')['prompt_tokens_mean'])}).",
        f"Lazy discovery pays {r(p,'lazy')['model_calls_mean'] - r(p,'static')['model_calls_mean']:.0f} extra model calls per task (one search per capability) and ends with {r(p,'lazy')['exposed_tools_mean']:.0f} schemas loaded.",
        f"With 10% malformed calls, the static registry lets {r('loud slips 10%','static')['backend_errors_mean']:.2f} bad calls per task reach the backend; schema validation in the scoped registry stops "
        f"{r('loud slips 10%','scoped')['rejected_pre_execution_mean']:.2f} per task before execution and {r('loud slips 10%','scoped')['backend_errors_mean']:.2f} reach the backend.",
    ]
    return experiment(
        "tools",
        "Tool registries and capability routing",
        "What does it cost to show the model every tool, and what do scoping and lazy loading buy?",
        {"tasks_per_cell": len(tasks), "catalogue": "4 task tools + 35 distractors + (lazy only) search_tools", "loop": "react"},
        [("arch", "Registry"), ("success_rate", "Success"), ("prompt_tokens_mean", "Prompt tokens"), ("model_calls_mean", "Model calls"), ("exposed_tools_mean", "Schemas exposed at end"), ("rejected_pre_execution_mean", "Rejected before backend"), ("backend_errors_mean", "Bad calls reaching backend")],
        ["scenario"],
        rows,
        findings,
        [
            "The simulated model never picks a wrong tool, so the accuracy cost of a crowded tool list (reported in RAG-MCP, arXiv:2505.03275) is not reproduced; only the token cost is measured.",
            "Search is keyword matching over 40 tools. Retrieval quality at thousands of tools is a separate problem.",
            "Prompt caching, which discounts repeated tool schemas on real APIs, is not modelled.",
        ],
    )
