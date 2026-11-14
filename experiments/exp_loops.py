"""E1 - execution loops: ReAct vs Plan-and-Execute vs Verified graph."""
from __future__ import annotations

from agentlab.eval.harness import run_loop
from agentlab.sim.model import ModelProfile
from agentlab.sim.tasks import make_suite

from .common import cell, experiment, find, pct

SCENARIOS = {
    "clean": dict(stages=2, lookups=3, moved=0, slip=0.0),
    "surprises": dict(stages=2, lookups=3, moved=2, slip=0.0),
    "noisy": dict(stages=2, lookups=3, moved=0, slip=0.08),
    "noisy+surprises": dict(stages=2, lookups=3, moved=2, slip=0.08),
    "long-noisy": dict(stages=4, lookups=3, moved=0, slip=0.08),
}
ARCHS = {
    "react": ("react", {}),
    "plan_execute": ("plan_execute", {}),
    "verified_graph": ("verified_graph", {"verify": "effects"}),
    "verified_graph[all]": ("verified_graph", {"verify": "all"}),
}


def run(n: int = 200) -> dict:
    rows = []
    for sc, p in SCENARIOS.items():
        tasks = make_suite(n, stages=p["stages"], lookups=p["lookups"], moved=p["moved"])
        profile = ModelProfile(slip_rate=p["slip"], silent_fraction=0.5, verifier_miss_rate=0.1)
        for arch, (loop, kw) in ARCHS.items():
            rows.append(cell({"scenario": sc, "arch": arch, "steps": len(tasks[0].steps)}, [run_loop(loop, t, profile, seed=11, loop_kwargs=kw) for t in tasks]))
    r = lambda sc, a: find(rows, scenario=sc, arch=a)
    findings = [
        f"With a perfect model and no surprises all loops succeed; plan-and-execute uses {r('clean','plan_execute')['model_calls_mean']:.0f} model calls and "
        f"{r('clean','plan_execute')['total_tokens_mean']:.0f} tokens per task versus {r('clean','react')['model_calls_mean']:.0f} calls and {r('clean','react')['total_tokens_mean']:.0f} tokens for ReAct "
        f"({pct(r('clean','plan_execute')['total_tokens_mean'], r('clean','react')['total_tokens_mean'])} tokens).",
        f"Two relocated keys cost ReAct {r('surprises','react')['model_calls_mean'] - r('clean','react')['model_calls_mean']:.0f} extra model calls and plan-and-execute "
        f"{r('surprises','plan_execute')['replans_mean']:.0f} replans; plan-and-execute tokens rise {pct(r('surprises','plan_execute')['total_tokens_mean'], r('clean','plan_execute')['total_tokens_mean'])} but stay below ReAct.",
        f"At an 8% slip rate (half silent) ReAct and plan-and-execute succeed on {r('noisy','react')['success_rate']:.0%} and {r('noisy','plan_execute')['success_rate']:.0%} of tasks - identical, because neither can see a silent error. "
        f"The verified graph reaches {r('noisy','verified_graph')['success_rate']:.0%} for {r('noisy','verified_graph')['total_tokens_mean']:.0f} tokens.",
        f"On {r('long-noisy','react')['steps']}-step tasks the gap widens: {r('long-noisy','react')['success_rate']:.0%} (ReAct) vs {r('long-noisy','verified_graph')['success_rate']:.0%} (verified graph). "
        f"ReAct's peak context is {r('long-noisy','react')['peak_context_mean']:.0f} tokens and its total is {r('long-noisy','react')['total_tokens_mean']:.0f}.",
        f"Auditing after every step instead of only before side effects changes success from {r('noisy','verified_graph')['success_rate']:.0%} to {r('noisy','verified_graph[all]')['success_rate']:.0%} "
        f"and model calls from {r('noisy','verified_graph')['model_calls_mean']:.1f} to {r('noisy','verified_graph[all]')['model_calls_mean']:.1f}.",
    ]
    return experiment(
        "loops",
        "Execution loops",
        "How do interleaved, plan-first and verified loops trade model calls, tokens and correctness?",
        {"tasks_per_cell": n, "seed": 11, "silent_fraction": 0.5, "verifier_miss_rate": 0.1, "scenarios": SCENARIOS},
        [("arch", "Architecture"), ("success_rate", "Success"), ("model_calls_mean", "Model calls"), ("tool_calls_mean", "Tool calls"), ("total_tokens_mean", "Tokens"), ("peak_context_mean", "Peak context"), ("replans_mean", "Replans"), ("repairs_mean", "Repairs")],
        ["scenario"],
        rows,
        findings,
        [
            "The simulated model never mis-plans structurally; real planners also omit or mis-order steps, which favours interleaved loops more than shown here.",
            "Slip probability is independent per attempt and identical across loops (paired draws). Real models make correlated errors.",
            "The verifier is modelled as an independent check with a fixed miss rate; a verifier that shares the actor's blind spots would catch less.",
        ],
    )
