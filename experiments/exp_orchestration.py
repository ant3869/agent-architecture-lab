"""E5 - orchestration: one agent vs supervisor-worker vs peer handoff."""
from __future__ import annotations

from agentlab.core.runtime import Meter
from agentlab.core.util import SimClock
from agentlab.eval.harness import run_loop
from agentlab.orchestration.handoff import HandoffSwarm
from agentlab.orchestration.supervisor import SupervisorWorkers
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import Task, evaluate, make_suite
from agentlab.sim.world import World
from agentlab.tools.registry import world_tools

from .common import cell, experiment, find, pct, ratio

EXTRA = ("makespan_ms", "messages", "message_tokens", "reassignments")


def run_orch(kind: str, task: Task, **kw) -> dict:
    clock = SimClock()
    world, meter = World(task, clock), Meter()
    model = SimModel(ModelProfile(), task, 0)
    cls = SupervisorWorkers if kind == "supervisor" else HandoffSwarm
    res = cls(model, world_tools(world), clock=clock, meter=meter, **kw).run(task)
    out = evaluate(task, world)
    return {
        "success": out.success and res.status == "final", "reason": out.reason if res.status == "final" or not out.success else "aborted",
        "iterations": meter.tool_calls, "replans": 0, "repairs": 0, "model_calls": meter.model_calls, "tool_calls": meter.tool_calls,
        "backend_calls": len(world.calls), "prompt_tokens": meter.prompt_tokens, "completion_tokens": meter.completion_tokens,
        "total_tokens": meter.total_tokens, "peak_context": meter.peak_prompt_tokens, "cost": meter.cost, "sim_ms": clock.now_ms,
        "duplicate_effects": out.duplicate_effects, "makespan_ms": res.makespan_ms, "messages": res.messages,
        "message_tokens": res.message_tokens, "reassignments": res.reassignments,
    }


def single(task: Task) -> dict:
    r = run_loop("react", task)
    return {**r, "makespan_ms": r["sim_ms"], "messages": 0, "message_tokens": 0, "reassignments": 0}


NOFAULT = {
    "single agent (react)": single,
    "supervisor, 1 worker/skill": lambda t: run_orch("supervisor", t),
    "supervisor, 3 workers/skill": lambda t: run_orch("supervisor", t, pool={"data": 3, "math": 3, "ops": 3}),
    "peer handoff": lambda t: run_orch("handoff", t),
}
CRASH = {
    "supervisor (respawn)": lambda t, k: run_orch("supervisor", t, crash={"ops-1": k}),
    "supervisor (respawn) + idem": lambda t, k: run_orch("supervisor", t, crash={"ops-1": k}, idempotent=True),
    "peer handoff": lambda t, k: run_orch("handoff", t, crash={"ops-1": k}),
    "peer handoff, durable baton + replica": lambda t, k: run_orch("handoff", t, crash={"ops-1": k}, redeliver=True, replicas={"ops": 2}),
    "peer handoff, durable baton + replica + idem": lambda t, k: run_orch("handoff", t, crash={"ops-1": k}, redeliver=True, replicas={"ops": 2}, idempotent=True),
}
CRASH_SCENARIO = "ops agent dies right after its k-th tool call, k in 1..4 (4 stages, per-stage notifications)"


def run(n: int = 200) -> dict:
    rows = []
    m = max(10, n // 4)
    big = ""
    for stages in (2, 4, 8):
        tasks = make_suite(m, stages=stages, lookups=3)
        big = f"no fault, {stages} stages ({len(tasks[0].steps)} steps)"
        for name, fn in NOFAULT.items():
            rows.append(cell({"scenario": big, "arch": name}, [fn(t) for t in tasks], EXTRA))
    steps = len(tasks[0].steps)
    tasks = make_suite(m, stages=4, lookups=3, notify_stages=True)
    for name, fn in CRASH.items():
        rows.append(cell({"scenario": CRASH_SCENARIO, "arch": name}, [fn(t, 1 + i % 4) for i, t in enumerate(tasks)], EXTRA))
    r = lambda sc, a: find(rows, scenario=sc, arch=a)
    cs = CRASH_SCENARIO
    findings = [
        f"On {steps}-step decomposable tasks the supervisor uses {r(big,'supervisor, 1 worker/skill')['total_tokens_mean']:.0f} tokens vs {r(big,'single agent (react)')['total_tokens_mean']:.0f} for one ReAct agent "
        f"({pct(r(big,'supervisor, 1 worker/skill')['total_tokens_mean'], r(big,'single agent (react)')['total_tokens_mean'])}): each worker starts from a fresh context (peak {r(big,'supervisor, 1 worker/skill')['peak_context_mean']:.0f} vs {r(big,'single agent (react)')['peak_context_mean']:.0f} tokens).",
        f"Peer handoff is the most expensive: {r(big,'peer handoff')['total_tokens_mean']:.0f} tokens ({ratio(r(big,'peer handoff')['total_tokens_mean'], r(big,'single agent (react)')['total_tokens_mean'])} the single agent), because the full transcript travels with every one of "
        f"{r(big,'peer handoff')['messages_mean']:.0f} handoffs and each handoff is an extra model call.",
        f"Parallel workers cut wall-clock: makespan {r(big,'supervisor, 3 workers/skill')['makespan_ms_mean'] / 1000:.1f}s with 3 workers per skill vs {r(big,'supervisor, 1 worker/skill')['makespan_ms_mean'] / 1000:.1f}s with 1 and "
        f"{r(big,'single agent (react)')['makespan_ms_mean'] / 1000:.1f}s single-agent, for the same total tokens.",
        f"The supervisor makes more model calls than the single agent ({r(big,'supervisor, 1 worker/skill')['model_calls_mean']:.0f} vs {r(big,'single agent (react)')['model_calls_mean']:.0f}): coordination adds calls even while it removes tokens.",
        f"Agent crash: the supervisor reassigns and finishes {r(cs,'supervisor (respawn)')['success_rate']:.0%} correctly (the rest duplicate a notification), {r(cs,'supervisor (respawn) + idem')['success_rate']:.0%} with idempotency keys. "
        f"A plain handoff chain finishes {r(cs,'peer handoff')['success_rate']:.0%}; with a durable baton and a replica {r(cs,'peer handoff, durable baton + replica')['success_rate']:.0%}, and {r(cs,'peer handoff, durable baton + replica + idem')['success_rate']:.0%} with keys.",
    ]
    return experiment(
        "orchestration",
        "Multi-agent orchestration",
        "When does splitting work across agents pay off, and which topology survives an agent crash?",
        {"tasks_per_cell": m, "model": "slip_rate=0", "worker_loop": "react", "latency_ms": {"model": 800, "lookup": 40, "compute": 5, "write": 60, "send": 120}, "crash_detection_timeout_ms": 5000},
        [("arch", "Architecture"), ("success_rate", "Success"), ("model_calls_mean", "Model calls"), ("total_tokens_mean", "Tokens"), ("peak_context_mean", "Peak context"), ("messages_mean", "Agent messages"), ("makespan_ms_mean", "Makespan (ms)"), ("duplicate_effects_mean", "Duplicate effects")],
        ["scenario"],
        rows,
        findings,
        [
            "Tasks decompose cleanly and the decomposition is always correct. A published taxonomy (MAST, arXiv:2503.13657) lists 14 failure modes observed in real multi-agent systems; this simulator models exactly one failure class, an agent crash.",
            "Workers return compact structured facts. Open-ended research tasks return long prose and can use far more tokens than a single agent (Anthropic reports about 15x chat usage for its multi-agent research system).",
            "Parallelism is a virtual-time schedule computed from measured per-subtask durations, not real concurrent execution.",
        ],
    )
