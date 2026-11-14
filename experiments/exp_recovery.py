"""E3 - failure recovery: who retries, where, and what it costs."""
from __future__ import annotations

from agentlab.eval.harness import run_loop
from agentlab.recovery.policies import CircuitBreakerTools, IdempotentTools, RetryingTools
from agentlab.sim.tasks import make_suite
from agentlab.sim.world import FaultPlan
from agentlab.tools.registry import StaticRegistry, world_tools

from .common import cell, experiment, find, ratio

FAULTS = {
    "transient 30%": lambda i: FaultPlan(i, transient={"lookup": 0.3, "write": 0.3, "send": 0.3}),
    "outage 58s": lambda i: FaultPlan(i, outages=[("lookup", 2000, 60000)]),
    "ambiguous timeout 50%": lambda i: FaultPlan(i, ambiguous={"send": 0.5}),
}


def stack(kind: str, task_id: str):
    def wrap(tools, world):
        if kind == "model-mediated":
            return tools
        if kind.startswith("backoff"):
            out = RetryingTools(tools, world.clock)
        else:
            with_replica = StaticRegistry(world_tools(world, ("lookup", "lookup_replica", "compute", "write", "send")))
            out = CircuitBreakerTools(RetryingTools(with_replica, world.clock), world.clock, threshold=3, cooldown_ms=5000, fallbacks={"lookup": "lookup_replica"})
        return IdempotentTools(out, task_id) if kind.endswith("+idem") else out

    return wrap


KINDS = ("model-mediated", "backoff", "backoff+idem", "breaker+fallback", "breaker+fallback+idem")


def run(n: int = 200) -> dict:
    tasks = make_suite(max(10, n // 2), stages=2, lookups=3)
    rows = []
    for fname, mk in FAULTS.items():
        for kind in KINDS:
            rows.append(cell({"scenario": fname, "arch": kind}, [run_loop("react", t, faults=mk(i), wrap=stack(kind, t.id)) for i, t in enumerate(tasks)]))
    r = lambda sc, a: find(rows, scenario=sc, arch=a)
    findings = [
        f"Transient faults: everything completes, but model-mediated retry spends {r('transient 30%','model-mediated')['model_calls_mean']:.1f} model calls per task versus {r('transient 30%','backoff')['model_calls_mean']:.1f} with runtime backoff "
        f"({r('transient 30%','model-mediated')['total_tokens_mean']:.0f} vs {r('transient 30%','backoff')['total_tokens_mean']:.0f} tokens).",
        f"Sustained outage: backoff alone makes {r('outage 58s','backoff')['backend_calls_mean']:.0f} backend calls and takes {r('outage 58s','backoff')['sim_ms_mean'] / 1000:.0f}s; breaker + replica fallback makes "
        f"{r('outage 58s','breaker+fallback')['backend_calls_mean']:.0f} and takes {r('outage 58s','breaker+fallback')['sim_ms_mean'] / 1000:.0f}s ({ratio(r('outage 58s','backoff')['sim_ms_mean'], r('outage 58s','breaker+fallback')['sim_ms_mean'])} faster).",
        f"Ambiguous timeouts on a non-idempotent tool: without idempotency keys every stack succeeds on only {r('ambiguous timeout 50%','backoff')['success_rate']:.0%} of tasks (duplicate sends); "
        f"with keys {r('ambiguous timeout 50%','backoff+idem')['success_rate']:.0%} and {r('ambiguous timeout 50%','breaker+fallback+idem')['success_rate']:.0%}.",
    ]
    return experiment(
        "recovery",
        "Failure handling and retries",
        "Should the model, the runtime, or a circuit breaker handle tool failures - and when is a retry unsafe?",
        {"tasks_per_cell": len(tasks), "loop": "react", "retry": "max 4 attempts, 100ms base, 2s cap, full jitter", "breaker": "threshold 3, cooldown 5s, lookup -> lookup_replica", "timeout_ms": 1000},
        [("arch", "Strategy"), ("success_rate", "Success"), ("model_calls_mean", "Model calls"), ("backend_calls_mean", "Backend calls"), ("total_tokens_mean", "Tokens"), ("sim_ms_mean", "Sim time (ms)"), ("duplicate_effects_mean", "Duplicate effects")],
        ["scenario"],
        rows,
        findings,
        [
            "Fault processes are independent per call; real outages are correlated across tools and time.",
            "The replica always holds fresh data. A stale replica would turn the fallback into a silent-error source.",
            "Simulated time: latencies and timeouts are fixed constants, not distributions.",
        ],
    )
