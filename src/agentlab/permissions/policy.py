"""Authorization middleware: three enforcement models for tool calls.

* `AllowlistTools`   - coarse: which tool names may be called at all.
* `ApprovalTools`    - risk-tiered: reads run, risky tiers pause for a human decision.
* `CapabilityTools`  - fine-grained, attenuable tokens that constrain tools *and arguments*.

All enforcement happens outside the model. A prompt cannot widen any of these.
"""
from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Callable

from ..core.trace import fingerprint_call
from ..core.types import Interrupt, ToolCall, ToolExecutor, ToolResult, ToolSpec
from ..core.util import SimClock


def _denied(code: str, why: str) -> ToolResult:
    return ToolResult(False, error_code=code, error=why)


class AllowlistTools:
    def __init__(self, inner: ToolExecutor, allowed: set[str]):
        self.inner, self.allowed = inner, set(allowed)
        self.denials = 0

    def specs(self) -> list[ToolSpec]:
        return [s for s in self.inner.specs() if s.name in self.allowed]

    def execute(self, call: ToolCall) -> ToolResult:
        if call.tool not in self.allowed:
            self.denials += 1
            return _denied("PERMISSION_DENIED", f"{call.tool} is not on the allowlist")
        return self.inner.execute(call)


Approver = Callable[[ToolCall], bool]


class ApprovalTools:
    """Human-in-the-loop gate keyed on each tool's risk tier (`ToolSpec.effect`).

    With an `approver` callback the decision is taken inline. Without one the wrapper
    raises `Interrupt`; the loop returns `interrupted`, the run can be persisted, and it
    resumes after `grant(call)` (approve) or with a denial settled by the loop.
    """

    def __init__(self, inner: ToolExecutor, approver: Approver | None = None, ask: tuple[str, ...] = ("external",)):
        self.inner, self.approver, self.ask = inner, approver, ask
        self.requests = 0
        self.denials = 0
        self.audit: list[dict[str, Any]] = []
        self._granted: set[str] = set()

    def specs(self) -> list[ToolSpec]:
        return self.inner.specs()

    def grant(self, call: ToolCall) -> None:
        """One-shot approval for exactly this call."""
        self._granted.add(fingerprint_call(call))

    def execute(self, call: ToolCall) -> ToolResult:
        spec = next((s for s in self.inner.specs() if s.name == call.tool), None)
        if spec is None or spec.effect not in self.ask:
            return self.inner.execute(call)
        fp = fingerprint_call(call)
        if fp in self._granted:
            self._granted.discard(fp)
            self.audit.append({"call": call.tool, "args": dict(call.args), "decision": "approved"})
            return self.inner.execute(call)
        self.requests += 1
        if self.approver is None:
            raise Interrupt({"reason": "approval_required", "tool": call.tool, "args": dict(call.args)})
        approved = self.approver(call)
        self.audit.append({"call": call.tool, "args": dict(call.args), "decision": "approved" if approved else "denied"})
        if not approved:
            self.denials += 1
            return _denied("APPROVAL_DENIED", "a human reviewer denied this action")
        return self.inner.execute(call)


# -- capability tokens -----------------------------------------------------------
@dataclass(frozen=True)
class Capability:
    """A bearer token in the style of macaroons (Birgisson et al., NDSS 2014).

    `sig` is an HMAC chain over the id and every caveat. A holder can append a caveat
    (narrowing the token) without the root secret, but cannot remove one.
    """

    id: str
    caveats: tuple[str, ...]
    sig: str


def _mac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def mint(secret: bytes, cap_id: str, *caveats: dict[str, Any]) -> Capability:
    cap = Capability(cap_id, (), _mac(secret, cap_id).hex())
    for c in caveats:
        cap = attenuate(cap, c)
    return cap


def attenuate(cap: Capability, caveat: dict[str, Any]) -> Capability:
    text = json.dumps(caveat, sort_keys=True)
    return Capability(cap.id, cap.caveats + (text,), _mac(bytes.fromhex(cap.sig), text).hex())


def verify_signature(secret: bytes, cap: Capability) -> bool:
    sig = _mac(secret, cap.id)
    for c in cap.caveats:
        sig = _mac(sig, c)
    return hmac.compare_digest(sig.hex(), cap.sig)


def check_caveats(cap: Capability, call: ToolCall, now_ms: int, calls_used: int) -> str:
    """Return '' if every caveat admits the call, else the reason it is refused."""
    for text in cap.caveats:
        c = json.loads(text)
        if "tools" in c and call.tool not in c["tools"]:
            return f"tool {call.tool} outside token scope"
        if "arg" in c:
            a = c["arg"]
            if call.tool == a["tool"] and not fnmatch.fnmatchcase(str(call.args.get(a["name"], "")), a["pattern"]):
                return f"{a['tool']}.{a['name']} must match {a['pattern']}"
        if "max_calls" in c and calls_used >= c["max_calls"]:
            return "call budget exhausted"
        if "not_after_ms" in c and now_ms > c["not_after_ms"]:
            return "token expired"
    return ""


class CapabilityTools:
    def __init__(self, inner: ToolExecutor, secret: bytes, cap: Capability, clock: SimClock | None = None):
        self.inner, self.secret, self.cap = inner, secret, cap
        self.clock = clock or SimClock()
        self.calls_used = 0
        self.denials = 0

    def specs(self) -> list[ToolSpec]:
        scopes = [set(json.loads(c)["tools"]) for c in self.cap.caveats if "tools" in json.loads(c)]
        return [s for s in self.inner.specs() if all(s.name in sc for sc in scopes)]

    def execute(self, call: ToolCall) -> ToolResult:
        if not verify_signature(self.secret, self.cap):
            self.denials += 1
            return _denied("CAPABILITY_DENIED", "invalid token signature")
        why = check_caveats(self.cap, call, self.clock.now_ms, self.calls_used)
        if why:
            self.denials += 1
            return _denied("CAPABILITY_DENIED", why)
        self.calls_used += 1
        return self.inner.execute(call)
