"""Crash injection and the recovery strategies compared in the durability experiment.

A crash kills the agent process (all in-memory state is lost). The world and the
durable stores survive. `phase` places the crash relative to the n-th tool call:
"before" = the call never reached the backend; "after" = the backend applied it but
the agent died before recording the result - the classic at-least-once window.
"""
from __future__ import annotations

from typing import Any

from ..core.runtime import Meter, Runtime
from ..core.types import SimulatedCrash, ToolCall, ToolExecutor, ToolResult, ToolSpec
from ..core.util import SimClock
from ..loops.base import LoopResult
from ..loops.react import ReActLoop
from ..loops.verified_graph import VerifiedGraphLoop
from ..recovery.policies import IdempotentTools
from ..sim.model import ModelProfile, SimModel
from ..sim.tasks import Task, evaluate
from ..sim.world import World
from ..tools.registry import StaticRegistry, world_tools
from .journal import DurableSession
from .stores import SQLiteCheckpointer, SQLiteJournal

STRATEGIES = ("restart", "snapshot", "snapshot+idem", "graph_checkpoint", "graph_checkpoint+idem", "journal", "journal+idem")


class CrashSchedule:
    """Crash points over the cumulative tool-call count across process incarnations. Each fires once."""

    def __init__(self, points: list[tuple[int, str]]):
        for _, phase in points:
            if phase not in ("before", "after"):
                raise ValueError("phase must be 'before' or 'after'")
        self.points = set(points)
        self.n = 0


class CrashingTools:
    def __init__(self, inner: ToolExecutor, schedule: CrashSchedule):
        self.inner, self.schedule = inner, schedule

    def specs(self) -> list[ToolSpec]:
        return self.inner.specs()

    def execute(self, call: ToolCall) -> ToolResult:
        s = self.schedule
        s.n += 1
        n = s.n
        if (n, "before") in s.points:
            s.points.discard((n, "before"))
            raise SimulatedCrash(f"crash before tool call {n}")
        result = self.inner.execute(call)
        if (n, "after") in s.points:
            s.points.discard((n, "after"))
            raise SimulatedCrash(f"crash after tool call {n}")
        return result


def run_with_crashes(
    strategy: str,
    task: Task,
    profile: ModelProfile | None = None,
    seed: int = 0,
    crashes: list[tuple[int, str]] | None = None,
    max_incarnations: int = 12,
) -> dict[str, Any]:
    """Run `task` under `strategy`, crashing at the given points and recovering each time."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    clock = SimClock()
    world = World(task, clock)
    meter = Meter()
    schedule = CrashSchedule(list(crashes or []))
    checkpoints = SQLiteCheckpointer()
    journal = SQLiteJournal()
    base, _, idem = strategy.partition("+")
    result: LoopResult | None = None
    restarts = 0
    for incarnation in range(max_incarnations):
        model = SimModel(profile or ModelProfile(), task, seed)  # a fresh process: nothing carried in memory
        tools: ToolExecutor = CrashingTools(StaticRegistry(world_tools(world)), schedule)
        if idem and base != "journal":
            tools = IdempotentTools(tools, namespace=task.id)
        try:
            if base == "restart":
                result = ReActLoop(Runtime(model, tools, clock=clock, meter=meter)).run(task.goal_message())
            elif base == "snapshot":
                saved = checkpoints.latest(task.id)
                loop = ReActLoop(Runtime(model, tools, clock=clock, meter=meter), on_step=lambda h: checkpoints.put(task.id, {"history": h}))
                result = loop.run(task.goal_message(), resume=saved["history"] if saved else None)
            elif base == "graph_checkpoint":
                loop_g = VerifiedGraphLoop(Runtime(model, tools, clock=clock, meter=meter), checkpointer=checkpoints, thread_id=task.id)
                result = loop_g.resume() if incarnation else loop_g.run(task.goal_message())
            else:  # journal
                session = DurableSession(journal, task.id, idempotency_keys=bool(idem))
                rt = Runtime(session.model(model), session.tools(tools), clock=clock, meter=meter)
                result = ReActLoop(rt).run(task.goal_message())
            break
        except SimulatedCrash:
            restarts += 1
    out = evaluate(task, world)
    return {
        "success": out.success and result is not None and result.status == "final",
        "reason": out.reason if result is not None else "never_recovered",
        "restarts": restarts,
        "model_calls": meter.model_calls,
        "tool_calls": meter.tool_calls,
        "backend_calls": len(world.calls),
        "total_tokens": meter.total_tokens,
        "duplicate_effects": out.duplicate_effects,
        "deduped_calls": sum(1 for c in world.calls if c.get("deduped")),
        "store_bytes": checkpoints.bytes_written + journal.bytes_written,
        "store_writes": checkpoints.writes + journal.writes,
        "sim_ms": clock.now_ms,
    }
