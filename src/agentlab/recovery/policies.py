"""Failure-handling middleware for tool executors. Each wrapper is itself a ToolExecutor, so they compose.

Typical stack (outermost first):  IdempotentTools -> CircuitBreakerTools -> RetryingTools -> registry
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..core.types import ToolCall, ToolExecutor, ToolResult, ToolSpec
from ..core.util import SimClock, fingerprint, u01


class IdempotentTools:
    """Attach a deterministic idempotency key to every side-effecting call.

    The key is derived from the logical operation (namespace, intent, tool, args), so a
    repeat of the same operation - by a runtime retry, a model re-emission, or a resumed
    run - is collapsed by the backend instead of being applied twice.
    """

    def __init__(self, inner: ToolExecutor, namespace: str):
        self.inner, self.namespace = inner, namespace

    def specs(self) -> list[ToolSpec]:
        return self.inner.specs()

    def execute(self, call: ToolCall) -> ToolResult:
        spec = next((s for s in self.inner.specs() if s.name == call.tool), None)
        if spec is not None and spec.effect != "read" and not call.idem_key:
            call = replace(call, idem_key=fingerprint([self.namespace, call.step_id, call.tool, call.args]))
        return self.inner.execute(call)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_ms: int = 100
    cap_ms: int = 2000
    jitter: bool = True  # "full jitter": sleep ~ U(0, min(cap, base * 2^attempt))
    retry_non_idempotent: bool = False  # only safe when the call carries an idempotency key


class RetryingTools:
    """Bounded exponential backoff, applied below the model so retries cost no tokens."""

    def __init__(self, inner: ToolExecutor, clock: SimClock, policy: RetryPolicy | None = None, seed: int = 0):
        self.inner, self.clock, self.policy, self.seed = inner, clock, policy or RetryPolicy(), seed
        self.retries = 0
        self.waited_ms = 0

    def specs(self) -> list[ToolSpec]:
        return self.inner.specs()

    def execute(self, call: ToolCall) -> ToolResult:
        p = self.policy
        spec = next((s for s in self.inner.specs() if s.name == call.tool), None)
        safe = bool(call.idem_key) or p.retry_non_idempotent or (spec is not None and spec.idempotent)
        attempt = 1
        while True:
            result = self.inner.execute(call)
            if result.ok or not result.retryable or not safe or attempt >= p.max_attempts:
                return replace(result, attempts=attempt)
            delay = min(p.cap_ms, p.base_ms * 2 ** (attempt - 1))
            if p.jitter:
                delay *= u01(self.seed, "jitter", call.tool, self.retries)
            self.clock.advance(delay)
            self.waited_ms += int(round(delay))
            self.retries += 1
            attempt += 1


class CircuitBreakerTools:
    """Per-tool circuit breaker with optional fallback routing.

    closed -> (threshold consecutive retryable failures) -> open -> (cooldown) -> half-open probe.
    While open, calls are not sent to the failing backend: they go to the fallback tool if one
    is configured, otherwise they fail fast with CIRCUIT_OPEN.
    """

    def __init__(self, inner: ToolExecutor, clock: SimClock, threshold: int = 3, cooldown_ms: int = 5000, fallbacks: dict[str, str] | None = None):
        self.inner, self.clock = inner, clock
        self.threshold, self.cooldown_ms = threshold, cooldown_ms
        self.fallbacks = fallbacks or {}
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, int] = {}
        self.short_circuited = 0
        self.fallback_calls = 0
        self.opens = 0

    def specs(self) -> list[ToolSpec]:
        hidden = set(self.fallbacks.values())
        return [s for s in self.inner.specs() if s.name not in hidden]

    def state(self, tool: str) -> str:
        if tool not in self._opened_at:
            return "closed"
        return "open" if self.clock.now_ms - self._opened_at[tool] < self.cooldown_ms else "half_open"

    def _fallback(self, call: ToolCall) -> ToolResult | None:
        alt = self.fallbacks.get(call.tool)
        if alt is None:
            return None
        self.fallback_calls += 1
        return self.inner.execute(replace(call, tool=alt))

    def execute(self, call: ToolCall) -> ToolResult:
        tool = call.tool
        if self.state(tool) == "open":
            self.short_circuited += 1
            return self._fallback(call) or ToolResult(False, error_code="CIRCUIT_OPEN", error=f"{tool} circuit is open", retryable=True)
        result = self.inner.execute(call)
        if result.ok or not result.retryable:  # a caller error says nothing about backend health
            self._failures[tool] = 0
            self._opened_at.pop(tool, None)
            return result
        self._failures[tool] = self._failures.get(tool, 0) + 1
        if self._failures[tool] >= self.threshold or tool in self._opened_at:
            if tool not in self._opened_at or self.state(tool) == "half_open":
                self.opens += 1
            self._opened_at[tool] = self.clock.now_ms
        return self._fallback(call) or result
