from agentlab.core.types import ToolCall, ToolResult, ToolSpec
from agentlab.core.util import SimClock
from agentlab.eval.harness import run_loop
from agentlab.recovery.policies import CircuitBreakerTools, IdempotentTools, RetryingTools, RetryPolicy
from agentlab.sim.tasks import make_task
from agentlab.sim.world import FaultPlan
from agentlab.tools.registry import StaticRegistry, world_tools


class Flaky:
    """Fails `fail` times with a retryable error, then succeeds. Records every call it sees."""

    def __init__(self, fail, idempotent=True, retryable=True):
        self.fail, self.retryable, self.seen = fail, retryable, []
        self.spec = ToolSpec("op", "x", {}, "read" if idempotent else "external", idempotent)

    def specs(self):
        return [self.spec, ToolSpec("alt", "x", {})]

    def execute(self, call):
        self.seen.append(call)
        if call.tool == "alt":
            return ToolResult(True, "from-alt")
        if len([c for c in self.seen if c.tool == "op"]) <= self.fail:
            return ToolResult(False, error_code="TRANSIENT" if self.retryable else "BAD", retryable=self.retryable)
        return ToolResult(True, "ok")


CALL = ToolCall("op", {})


def test_backoff_retries_idempotent_calls_with_bounded_exponential_delay():
    clock, inner = SimClock(), Flaky(3)
    r = RetryingTools(inner, clock, RetryPolicy(max_attempts=5, base_ms=100, cap_ms=250, jitter=False)).execute(CALL)
    assert r.ok and r.attempts == 4 and clock.now_ms == 100 + 200 + 250
    clock, inner = SimClock(), Flaky(10)
    r = RetryingTools(inner, clock, RetryPolicy(max_attempts=3, jitter=False)).execute(CALL)
    assert not r.ok and r.attempts == 3 and len(inner.seen) == 3


def test_jitter_is_seeded_and_never_exceeds_the_deterministic_delay():
    def waited(seed):
        clock = SimClock()
        RetryingTools(Flaky(3), clock, RetryPolicy(max_attempts=5), seed=seed).execute(CALL)
        return clock.now_ms

    assert waited(1) == waited(1) != waited(2)
    assert all(waited(s) <= 100 + 200 + 400 for s in range(20))


def test_non_retryable_errors_and_non_idempotent_calls_are_not_retried():
    inner = Flaky(2, retryable=False)
    assert RetryingTools(inner, SimClock()).execute(CALL).attempts == 1
    inner = Flaky(2, idempotent=False)
    r = RetryingTools(inner, SimClock()).execute(CALL)
    assert not r.ok and len(inner.seen) == 1, "blind retry of a non-idempotent call would risk a duplicate effect"
    inner = Flaky(2, idempotent=False)
    assert IdempotentTools(RetryingTools(inner, SimClock()), "ns").execute(CALL).ok
    assert len({c.idem_key for c in inner.seen}) == 1 and inner.seen[0].idem_key


def test_idempotency_keys_identify_the_logical_operation():
    inner = Flaky(0, idempotent=False)
    w = IdempotentTools(inner, "run-1")
    w.execute(ToolCall("op", {"x": 1}, "s1"))
    w.execute(ToolCall("op", {"x": 1}, "s1"))
    w.execute(ToolCall("op", {"x": 2}, "s1"))
    w.execute(ToolCall("op", {"x": 1}, "s2"))
    IdempotentTools(inner, "run-2").execute(ToolCall("op", {"x": 1}, "s1"))
    keys = [c.idem_key for c in inner.seen]
    assert keys[0] == keys[1] and len(set(keys)) == 4
    reads = Flaky(0)
    IdempotentTools(reads, "ns").execute(CALL)
    assert reads.seen[0].idem_key == "", "reads need no key"


def test_circuit_breaker_state_machine():
    clock, inner = SimClock(), Flaky(10**6)
    cb = CircuitBreakerTools(inner, clock, threshold=3, cooldown_ms=1000)
    for _ in range(3):
        assert cb.execute(CALL).error_code == "TRANSIENT"
    assert cb.state("op") == "open" and cb.opens == 1
    assert cb.execute(CALL).error_code == "CIRCUIT_OPEN" and len(inner.seen) == 3, "open circuit must not touch the backend"
    clock.advance(1000)
    assert cb.state("op") == "half_open"
    cb.execute(CALL)
    assert len(inner.seen) == 4 and cb.state("op") == "open" and cb.opens == 2, "failed probe re-opens"
    clock.advance(1000)
    inner.fail = 0
    assert cb.execute(CALL).ok and cb.state("op") == "closed"


def test_breaker_ignores_caller_errors_and_routes_to_fallback():
    clock, inner = SimClock(), Flaky(10**6, retryable=False)
    cb = CircuitBreakerTools(inner, clock, threshold=2)
    for _ in range(5):
        cb.execute(CALL)
    assert cb.state("op") == "closed", "a 4xx-style error says nothing about backend health"
    inner = Flaky(10**6)
    cb = CircuitBreakerTools(inner, clock, threshold=2, fallbacks={"op": "alt"})
    assert [s.name for s in cb.specs()] == ["op"], "the fallback tool is hidden from the model"
    assert [cb.execute(CALL).output for _ in range(4)] == ["from-alt"] * 4
    assert [c.tool for c in inner.seen] == ["op", "alt", "op", "alt", "alt", "alt"] and cb.short_circuited == 2


def test_end_to_end_outage_is_survived_fastest_with_breaker_and_fallback():
    t = make_task(6, stages=2, lookups=3)
    outage = lambda: FaultPlan(outages=[("lookup", 2000, 60000)])
    plain = run_loop("react", t, faults=outage())
    retry = run_loop("react", t, faults=outage(), wrap=lambda tools, w: RetryingTools(tools, w.clock))

    def breaker(tools, w):
        full = StaticRegistry(world_tools(w, ("lookup", "lookup_replica", "compute", "write", "send")))
        return CircuitBreakerTools(RetryingTools(full, w.clock), w.clock, fallbacks={"lookup": "lookup_replica"})

    fast = run_loop("react", t, faults=outage(), wrap=breaker)
    assert plain["success"] and retry["success"] and fast["success"]
    assert fast["sim_ms"] < retry["sim_ms"] / 2 and fast["model_calls"] == len(t.steps) + 1 < retry["model_calls"] < plain["model_calls"]


def test_lost_reply_on_send_needs_idempotency_keys():
    t = make_task(6, stages=1, lookups=2)
    faults = lambda: FaultPlan(seed=1, ambiguous={"send": 1.0})
    assert run_loop("react", t, faults=faults(), loop_kwargs={"max_iters": 12})["reason"] == "duplicate_effect"
    safe = run_loop("react", t, faults=faults(), wrap=lambda tools, w: IdempotentTools(tools, t.id))
    assert safe["success"], "the key lets the model's own re-emission be collapsed"
