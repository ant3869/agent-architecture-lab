"""E2 - durable execution: exhaustive single-crash and sampled double-crash recovery."""
from __future__ import annotations

from agentlab.core.util import u01
from agentlab.durability.crash import STRATEGIES, run_with_crashes
from agentlab.sim.tasks import make_suite

from .common import cell, experiment, find

EXTRA = ("restarts", "extra_model_calls", "extra_backend_calls", "store_bytes", "store_writes", "deduped_calls")


def run(n: int = 200) -> dict:
    tasks = make_suite(max(4, n // 10), stages=2, lookups=2, notify_stages=True)
    rows = []
    for strategy in STRATEGIES:
        single, double = [], []
        for t in tasks:
            base = run_with_crashes(strategy, t)
            calls = base["backend_calls"]

            def rec(crashes: list[tuple[int, str]]) -> dict:
                r = run_with_crashes(strategy, t, crashes=crashes)
                r["extra_model_calls"] = r["model_calls"] - base["model_calls"]
                r["extra_backend_calls"] = r["backend_calls"] - base["backend_calls"]
                return r

            for k in range(1, calls + 1):
                for phase in ("before", "after"):
                    single.append(rec([(k, phase)]))
            for j in range(10):
                a = 1 + int(u01("dbl", t.id, j, "a") * calls)
                b = a + 1 + int(u01("dbl", t.id, j, "b") * calls)
                double.append(rec([(a, "after"), (b, "before" if u01("dbl", t.id, j, "p") < 0.5 else "after")]))
        rows.append(cell({"scenario": "single crash (exhaustive)", "arch": strategy}, single, EXTRA))
        rows.append(cell({"scenario": "two crashes (sampled)", "arch": strategy}, double, EXTRA))
    r = lambda a: find(rows, scenario="single crash (exhaustive)", arch=a)
    findings = [
        f"Restart-from-scratch completes {r('restart')['success_rate']:.0%} of crashed runs correctly; every failure is a duplicated notification ({r('restart')['duplicate_effects_mean']:.2f} duplicates per run) "
        f"and it re-issues {r('restart')['extra_model_calls_mean']:.1f} model calls on average.",
        f"Snapshots and the journal both stop at {r('snapshot')['success_rate']:.0%} / {r('journal')['success_rate']:.0%} without idempotency keys: the failures are exactly the crashes that land between a non-idempotent effect and its record.",
        f"Adding idempotency keys closes that window for every strategy that persists progress: snapshot+idem {r('snapshot+idem')['success_rate']:.0%}, graph_checkpoint+idem {r('graph_checkpoint+idem')['success_rate']:.0%}, journal+idem {r('journal+idem')['success_rate']:.0%}.",
        f"Recovery cost in re-issued model calls: journal {r('journal')['extra_model_calls_mean']:.2f}, snapshot {r('snapshot')['extra_model_calls_mean']:.2f}, graph checkpoint {r('graph_checkpoint')['extra_model_calls_mean']:.2f}, restart {r('restart')['extra_model_calls_mean']:.2f}.",
        f"Bytes written to the durable store per run: journal {r('journal')['store_bytes_mean']:.0f}, per-iteration snapshot {r('snapshot')['store_bytes_mean']:.0f}, per-node graph checkpoint {r('graph_checkpoint')['store_bytes_mean']:.0f} "
        "(snapshots rewrite the whole growing state each time).",
    ]
    return experiment(
        "durability",
        "Durable execution and crash recovery",
        "After a process crash at any point, which persistence strategy finishes the task without repeating side effects, and at what cost?",
        {"tasks": len(tasks), "steps_per_task": len(tasks[0].steps), "crash_points": "every tool call x {before, after}", "double_crash_samples_per_task": 10, "model": "slip_rate=0"},
        [("arch", "Strategy"), ("n", "Runs"), ("success_rate", "Correct completion"), ("duplicate_effects_mean", "Duplicate effects"), ("extra_model_calls_mean", "Re-issued model calls"), ("extra_backend_calls_mean", "Re-executed tool calls"), ("store_bytes_mean", "Store bytes"), ("store_writes_mean", "Store writes")],
        ["scenario"],
        rows,
        findings,
        [
            "Crashes are injected only around tool calls, not inside model calls or store writes; torn writes are delegated to SQLite transactions.",
            "The backend honours idempotency keys perfectly and forever. Real APIs expire keys and some offer none.",
            "The journal relies on the agent code being deterministic; that holds here by construction and must be enforced in real code.",
        ],
    )
