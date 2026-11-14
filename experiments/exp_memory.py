"""E4 - context management: what the model sees as tasks get longer."""
from __future__ import annotations

from agentlab.eval.harness import run_loop
from agentlab.memory.context import Compaction, FactLedger, FullHistory, SlidingWindow
from agentlab.sim.tasks import make_suite

from .common import cell, experiment, find, pct

POLICIES = {
    "full": FullHistory,
    "window-6": lambda: SlidingWindow(6),
    "window-16": lambda: SlidingWindow(16),
    "window-32": lambda: SlidingWindow(32),
    "compaction-600": lambda: Compaction(600, keep_recent=4),
    "ledger": lambda: FactLedger(2),
}
LENGTHS = {"15 steps": 2, "29 steps": 4, "57 steps": 8}


def run(n: int = 200) -> dict:
    rows = []
    for label, stages in LENGTHS.items():
        tasks = make_suite(max(10, n // 2), stages=stages, lookups=3)
        assert label == f"{len(tasks[0].steps)} steps"
        cap = 4 * len(tasks[0].steps)
        for name, mk in POLICIES.items():
            rows.append(cell({"scenario": label, "arch": name}, [run_loop("react", t, loop_kwargs={"memory": mk(), "max_iters": cap}) for t in tasks]))
    r = lambda sc, a: find(rows, scenario=sc, arch=a)
    findings = [
        f"Full history grows quadratically: {r('15 steps','full')['total_tokens_mean']:.0f} tokens at 15 steps, {r('57 steps','full')['total_tokens_mean']:.0f} at 57 (peak context {r('57 steps','full')['peak_context_mean']:.0f}).",
        f"A 6-message window succeeds on {r('15 steps','window-6')['success_rate']:.0%} / {r('29 steps','window-6')['success_rate']:.0%} / {r('57 steps','window-6')['success_rate']:.0%} of tasks: it livelocks, re-fetching one evicted operand while the other falls out of the window "
        f"({r('15 steps','window-6')['tool_calls_mean']:.0f} tool calls until the iteration cap vs {r('15 steps','full')['tool_calls_mean']:.0f} needed).",
        f"A window large enough to finish is not automatically cheaper: at 57 steps window-16 uses {pct(r('57 steps','window-16')['total_tokens_mean'], r('57 steps','full')['total_tokens_mean'])} tokens vs full history and window-32 {pct(r('57 steps','window-32')['total_tokens_mean'], r('57 steps','full')['total_tokens_mean'])}, because re-fetching adds model calls.",
        f"A 16-message window succeeds on {r('15 steps','window-16')['success_rate']:.0%} / {r('29 steps','window-16')['success_rate']:.0%} / {r('57 steps','window-16')['success_rate']:.0%}; a 32-message window on "
        f"{r('15 steps','window-32')['success_rate']:.0%} / {r('29 steps','window-32')['success_rate']:.0%} / {r('57 steps','window-32')['success_rate']:.0%}, using {r('57 steps','window-32')['tool_calls_mean']:.1f} tool calls at 57 steps (vs {r('57 steps','full')['tool_calls_mean']:.1f} needed).",
        f"Compaction keeps 57-step tasks at {r('57 steps','compaction-600')['success_rate']:.0%} success with {pct(r('57 steps','compaction-600')['total_tokens_mean'], r('57 steps','full')['total_tokens_mean'])} tokens vs full history, "
        f"paying {r('57 steps','compaction-600')['model_calls_mean'] - r('57 steps','full')['model_calls_mean']:.1f} extra (summarisation) model calls.",
        f"The fact ledger is cheapest: {pct(r('57 steps','ledger')['total_tokens_mean'], r('57 steps','full')['total_tokens_mean'])} tokens at 57 steps, peak context {r('57 steps','ledger')['peak_context_mean']:.0f}, no extra model calls.",
    ]
    return experiment(
        "memory",
        "Context and memory management",
        "How should an agent bound its context as a task grows, and what breaks when it forgets?",
        {"tasks_per_cell": max(10, n // 2), "loop": "react", "model": "slip_rate=0", "max_iters": "4 x steps", "token_estimate": "chars/4"},
        [("arch", "Policy"), ("success_rate", "Success"), ("total_tokens_mean", "Tokens"), ("peak_context_mean", "Peak context"), ("model_calls_mean", "Model calls"), ("tool_calls_mean", "Tool calls"), ("duplicate_effects_mean", "Duplicate effects")],
        ["scenario"],
        rows,
        findings,
        [
            "The simulated summariser is lossless for task facts. Real summaries drop or distort details; treat the compaction numbers as an upper bound.",
            "The simulated model has no recall degradation with context length ('context rot'), so full history is never penalised for size, only charged for it.",
            "The ledger needs structured tool outputs keyed by step; free-text observations require a model call to extract facts.",
        ],
    )
