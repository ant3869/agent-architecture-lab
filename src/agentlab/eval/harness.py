"""Common evaluation harness: one way to build a run, one metric schema, one aggregator."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ..core.runtime import Meter, Runtime
from ..core.trace import Tracer
from ..core.types import Model, ToolExecutor
from ..core.util import SimClock
from ..loops.base import LoopResult
from ..loops.plan_execute import PlanExecuteLoop
from ..loops.react import ReActLoop
from ..loops.verified_graph import VerifiedGraphLoop
from ..sim.model import ModelProfile, SimModel
from ..sim.tasks import Task, evaluate
from ..sim.world import FaultPlan, World
from ..tools.registry import StaticRegistry, world_tools

LOOPS: dict[str, Any] = {"react": ReActLoop, "plan_execute": PlanExecuteLoop, "verified_graph": VerifiedGraphLoop}


@dataclass
class Setup:
    task: Task
    world: World
    clock: SimClock
    tracer: Tracer
    meter: Meter
    model: Model
    tools: ToolExecutor
    rt: Runtime


def setup(
    task: Task,
    profile: ModelProfile | None = None,
    seed: int = 0,
    *,
    faults: FaultPlan | None = None,
    model: Model | None = None,
    wrap: Callable[[ToolExecutor, World], ToolExecutor] | None = None,
    trace: bool = False,
    world: World | None = None,
    meter: Meter | None = None,
    agent: str = "agent",
) -> Setup:
    """Assemble world + model + tools + runtime for one run. `wrap` layers tool middleware."""
    clock = world.clock if world else SimClock()
    world = world or World(task, clock, faults)
    tracer = Tracer(clock, enabled=trace)
    meter = meter or Meter()
    model = model or SimModel(profile or ModelProfile(), task, seed)
    tools: ToolExecutor = StaticRegistry(world_tools(world))
    if wrap:
        tools = wrap(tools, world)
    return Setup(task, world, clock, tracer, meter, model, tools, Runtime(model, tools, clock=clock, tracer=tracer, meter=meter, agent=agent))


def metrics(s: Setup, result: LoopResult | None = None, **extra: Any) -> dict[str, Any]:
    out = evaluate(s.task, s.world)
    m = s.meter
    row: dict[str, Any] = {
        "success": out.success,
        "reason": out.reason,
        "status": result.status if result else "",
        "iterations": result.iterations if result else 0,
        "replans": result.replans if result else 0,
        "repairs": result.repairs if result else 0,
        "model_calls": m.model_calls,
        "tool_calls": m.tool_calls,
        "backend_calls": len(s.world.calls),
        "prompt_tokens": m.prompt_tokens,
        "completion_tokens": m.completion_tokens,
        "total_tokens": m.total_tokens,
        "peak_context": m.peak_prompt_tokens,
        "cost": round(m.cost, 6),
        "sim_ms": s.clock.now_ms,
        "duplicate_effects": out.duplicate_effects,
        "wrong_effects": out.wrong_effects,
        "exfiltrated": out.exfiltrated,
        "steps": len(s.task.steps),
    }
    row.update(extra)
    return row


def run_loop(name: str, task: Task, profile: ModelProfile | None = None, seed: int = 0, loop_kwargs: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
    s = setup(task, profile, seed, **kw)
    result = LOOPS[name](s.rt, **(loop_kwargs or {})).run(task.goal_message())
    return metrics(s, result)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 4), round(min(1.0, c + h), 4))


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return float(v[min(len(v) - 1, max(0, math.ceil(q * len(v)) - 1))])


NUMERIC = ("iterations", "replans", "repairs", "model_calls", "tool_calls", "backend_calls", "prompt_tokens", "completion_tokens", "total_tokens", "peak_context", "cost", "sim_ms", "duplicate_effects")


def aggregate(rows: Iterable[dict[str, Any]], extra_numeric: Iterable[str] = ()) -> dict[str, Any]:
    rows = list(rows)
    n = len(rows)
    k = sum(1 for r in rows if r["success"])
    out: dict[str, Any] = {"n": n, "success_rate": round(k / n, 4) if n else 0.0, "success_ci95": list(wilson(k, n))}
    for key in (*NUMERIC, *extra_numeric):
        vals = [float(r[key]) for r in rows if key in r]
        if vals:
            out[f"{key}_mean"] = round(sum(vals) / len(vals), 3)
            out[f"{key}_p95"] = round(percentile(vals, 0.95), 3)
    out["reasons"] = dict(sorted(Counter(r["reason"] for r in rows).items()))
    return out
