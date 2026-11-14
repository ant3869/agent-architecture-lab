"""The simulated external world: a key-value store, a calculator and an outbox.

The world outlives agent crashes (it is "someone else's system"), supports
idempotency keys the way real payment/messaging APIs do, and injects faults
from a seeded `FaultPlan`.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any

from ..core.types import ToolCall, ToolResult, ToolSpec
from ..core.util import SimClock, u01
from .tasks import OPS, Task

KEY_RE = re.compile(r"^[a-z0-9:._-]+$")
LATENCY_MS = {"lookup": 40, "lookup_replica": 60, "compute": 5, "write": 60, "send": 120}
TIMEOUT_MS = 1000

WORLD_SPECS: dict[str, ToolSpec] = {
    "lookup": ToolSpec("lookup", "Read the value stored under a key in the inventory store.", {"key": "string"}, "read", True, "data", {"key": {"pattern": KEY_RE.pattern}}),
    "lookup_replica": ToolSpec("lookup_replica", "Read a key from the read replica of the inventory store.", {"key": "string"}, "read", True, "data", {"key": {"pattern": KEY_RE.pattern}}),
    "compute": ToolSpec("compute", "Apply op (add, sub, mul) to two numbers.", {"op": "string", "a": "number", "b": "number"}, "read", True, "math", {"op": {"enum": ["add", "sub", "mul"]}}),
    "write": ToolSpec("write", "Persist a value under a report key.", {"key": "string", "value": "any"}, "write", True, "ops", {"key": {"pattern": KEY_RE.pattern}}),
    "send": ToolSpec("send", "Send a notification to a recipient. Not idempotent.", {"to": "string", "body": "any"}, "external", False, "ops"),
}


class ToolFailure(Exception):
    def __init__(self, code: str, message: str, info: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.info = code, message, info or {}


@dataclass
class FaultPlan:
    seed: int = 0
    transient: dict[str, float] = field(default_factory=dict)  # tool -> P(TRANSIENT) per call
    outages: list[tuple[str, int, int]] = field(default_factory=list)  # (tool, start_ms, end_ms)
    ambiguous: dict[str, float] = field(default_factory=dict)  # tool -> P(effect applied, then TIMEOUT)

    def in_outage(self, tool: str, now_ms: int) -> bool:
        return any(t == tool and a <= now_ms < b for t, a, b in self.outages)


class World:
    def __init__(self, task: Task, clock: SimClock | None = None, faults: FaultPlan | None = None):
        self.task = task
        self.clock = clock or SimClock()
        self.faults = faults
        self.kv: dict[str, Any] = dict(task.kv)
        self.outbox: list[tuple[str, Any]] = []
        self.writes: list[tuple[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self._idem: dict[str, ToolResult] = {}
        self._count: Counter[str] = Counter()

    # -- public -----------------------------------------------------------------
    def call(self, tool: str, args: dict[str, Any], idem_key: str = "") -> ToolResult:
        self._count[tool] += 1
        rec = {"n": len(self.calls) + 1, "tool": tool, "args": dict(args), "t_ms": self.clock.now_ms}
        self.calls.append(rec)
        result = self._dispatch(tool, args, idem_key, self._count[tool])
        rec.update(ok=result.ok, code=result.error_code, deduped=result.deduped)
        return result

    def execute(self, call: ToolCall) -> ToolResult:
        return self.call(call.tool, call.args, call.idem_key)

    # -- internals --------------------------------------------------------------
    def _fail(self, code: str, msg: str, retryable: bool = False, info: dict[str, Any] | None = None) -> ToolResult:
        return ToolResult(False, error_code=code, error=msg, retryable=retryable, info=info or {})

    def _dispatch(self, tool: str, args: dict[str, Any], idem_key: str, n: int) -> ToolResult:
        if tool not in LATENCY_MS:
            return self._fail("UNKNOWN_TOOL", f"no such tool: {tool}")
        f = self.faults
        if f and f.in_outage(tool, self.clock.now_ms):
            self.clock.advance(TIMEOUT_MS)
            return self._fail("UNAVAILABLE", f"{tool} backend is not responding", retryable=True)
        if f and u01(f.seed, "transient", tool, n) < f.transient.get(tool, 0.0):
            self.clock.advance(LATENCY_MS[tool])
            return self._fail("TRANSIENT", f"{tool} failed transiently", retryable=True)
        self.clock.advance(LATENCY_MS[tool])
        if idem_key and idem_key in self._idem:
            return replace(self._idem[idem_key], deduped=True)
        try:
            output, note = getattr(self, f"_t_{tool}")(**args)
        except ToolFailure as e:
            return self._fail(e.code, e.message, info=e.info)
        except TypeError as e:
            return self._fail("INVALID_ARGS", str(e))
        result = ToolResult(True, output, note=note)
        if idem_key:
            self._idem[idem_key] = result
        if f and u01(f.seed, "ambiguous", tool, n) < f.ambiguous.get(tool, 0.0):
            self.clock.advance(TIMEOUT_MS)
            return self._fail("TIMEOUT", f"{tool} timed out; outcome unknown", retryable=True)
        return result

    def _t_lookup(self, key: str) -> tuple[Any, str]:
        if key in self.task.moved:
            new = self.task.moved[key]
            raise ToolFailure("MOVED", f"{key} moved to {new}", {"moved_to": new})
        if key not in self.kv:
            raise ToolFailure("NOT_FOUND", f"no such key: {key}")
        return self.kv[key], self.task.notes.get(key, "")

    _t_lookup_replica = _t_lookup

    def _t_compute(self, op: str, a: Any, b: Any) -> tuple[Any, str]:
        if op not in OPS:
            raise ToolFailure("INVALID_OP", f"unsupported op: {op}")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (a, b)):
            raise ToolFailure("INVALID_ARGS", "operands must be numbers")
        return OPS[op](a, b), ""

    def _t_write(self, key: str, value: Any) -> tuple[Any, str]:
        if not isinstance(key, str) or not KEY_RE.match(key):
            raise ToolFailure("INVALID_KEY", f"malformed key: {key}")
        self.kv[key] = value
        self.writes.append((key, value))
        return "written", ""

    def _t_send(self, to: str, body: Any) -> tuple[Any, str]:
        if to not in self.task.recipients:
            raise ToolFailure("UNKNOWN_RECIPIENT", f"no such recipient: {to}")
        self.outbox.append((to, body))
        return "sent", ""
