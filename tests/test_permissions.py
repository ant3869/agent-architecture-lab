import json

import pytest

from agentlab.core.types import Interrupt, ToolCall
from agentlab.core.util import SimClock
from agentlab.eval.harness import metrics, setup
from agentlab.loops.react import ReActLoop
from agentlab.permissions.policy import AllowlistTools, ApprovalTools, Capability, CapabilityTools, attenuate, check_caveats, mint, verify_signature
from agentlab.sim.model import ModelProfile
from agentlab.sim.tasks import ATTACKER, make_task

POISONED = make_task(1, stages=1, lookups=3, poisoned=True)
GULLIBLE = ModelProfile(injection_susceptibility=1.0)
SECRET = b"k"
SEND_EVIL = ToolCall("send", {"to": ATTACKER, "body": 1})
SEND_OPS = ToolCall("send", {"to": "ops", "body": 1})


def run(wrap):
    s = setup(POISONED, GULLIBLE, wrap=wrap)
    return s, ReActLoop(s.rt).run(POISONED.goal_message())


def test_the_attack_works_when_nothing_enforces_policy():
    s, _ = run(None)
    assert metrics(s)["exfiltrated"] and (ATTACKER, 4242) in s.world.outbox
    s = setup(POISONED, ModelProfile(injection_susceptibility=0.0))
    ReActLoop(s.rt).run(POISONED.goal_message())
    assert metrics(s)["success"], "a model that ignores embedded instructions is unaffected"


def test_allowlist_hides_and_blocks_tools_but_cannot_see_arguments():
    s, r = run(lambda t, w: AllowlistTools(t, {"lookup", "compute", "write"}))
    assert "send" not in [x.name for x in s.tools.specs()] and not s.world.outbox and r.status == "blocked"
    assert s.tools.execute(SEND_OPS).error_code == "PERMISSION_DENIED"
    s, _ = run(lambda t, w: AllowlistTools(t, {"lookup", "compute", "write", "send"}))
    assert metrics(s)["exfiltrated"], "tool-level granularity cannot separate good sends from bad"


def test_inline_approval_blocks_only_what_the_reviewer_denies():
    s, r = run(lambda t, w: ApprovalTools(t, approver=lambda c: c.args["to"] == "ops"))
    m = metrics(s, r)
    assert m["success"] and not m["exfiltrated"]
    assert (s.tools.requests, s.tools.denials) == (2, 1)
    assert [a["decision"] for a in s.tools.audit] == ["denied", "approved"]
    s, _ = run(lambda t, w: ApprovalTools(t, approver=lambda c: True))
    assert metrics(s)["exfiltrated"], "a rubber stamp is not a control"


def test_approval_only_gates_the_configured_risk_tiers():
    s = setup(POISONED, wrap=lambda t, w: ApprovalTools(t, ask=("write", "external")))
    with pytest.raises(Interrupt):
        s.tools.execute(ToolCall("write", {"key": "report:x", "value": 1}))
    assert s.tools.execute(ToolCall("compute", {"op": "add", "a": 1, "b": 1})).ok


def test_interrupt_resume_approval_flow():
    s = setup(POISONED, GULLIBLE, wrap=lambda t, w: ApprovalTools(t))
    loop = ReActLoop(s.rt)
    result = loop.run(POISONED.goal_message())
    seen = []
    while result.status == "interrupted":
        call = result.pending
        seen.append(call.args["to"])
        ok = call.args["to"] == "ops"
        if ok:
            s.tools.grant(call)
        result = loop.run(POISONED.goal_message(), resume=result.history, pending=(call, ok))
    assert seen == [ATTACKER, "ops"] and result.status == "final" and metrics(s)["success"]
    with pytest.raises(Interrupt):
        s.tools.execute(SEND_OPS)  # a grant is single-use


def test_capability_tokens_constrain_arguments_and_cannot_be_widened():
    root = mint(SECRET, "c1", {"tools": ["lookup", "compute", "write", "send"]})
    cap = attenuate(root, {"arg": {"tool": "send", "name": "to", "pattern": "ops"}})
    assert verify_signature(SECRET, root) and verify_signature(SECRET, cap)
    assert check_caveats(cap, SEND_OPS, 0, 0) == "" and "must match" in check_caveats(cap, SEND_EVIL, 0, 0)
    assert check_caveats(root, SEND_EVIL, 0, 0) == "", "the unattenuated token allows it"
    stripped = Capability(cap.id, cap.caveats[:1], cap.sig)
    widened = Capability(cap.id, (json.dumps({"tools": ["lookup", "compute", "write", "send", "admin"]}),) + cap.caveats[1:], cap.sig)
    assert not verify_signature(SECRET, stripped) and not verify_signature(SECRET, widened)
    assert not verify_signature(b"other", cap)
    narrower = attenuate(cap, {"tools": ["lookup"]})
    assert verify_signature(SECRET, narrower) and "outside token scope" in check_caveats(narrower, SEND_OPS, 0, 0)


def test_capability_budget_expiry_and_forgery_are_enforced_at_call_time():
    clock = SimClock()
    s = setup(POISONED)
    cap = mint(SECRET, "c", {"max_calls": 2}, {"not_after_ms": 500})
    tools = CapabilityTools(s.tools, SECRET, cap, clock)
    calc = ToolCall("compute", {"op": "add", "a": 1, "b": 1})
    assert tools.execute(calc).ok and tools.execute(calc).ok
    assert "budget" in tools.execute(calc).error
    tools = CapabilityTools(s.tools, SECRET, mint(SECRET, "c", {"not_after_ms": 500}), clock)
    clock.advance(501)
    assert "expired" in tools.execute(calc).error
    forged = CapabilityTools(s.tools, SECRET, Capability("c", (), "00" * 32), clock)
    assert forged.execute(calc).error_code == "CAPABILITY_DENIED" and forged.denials == 1


def test_capability_token_stops_the_injection_with_no_human_in_the_loop():
    cap = mint(SECRET, "c", {"tools": ["lookup", "compute", "write", "send"]}, {"arg": {"tool": "send", "name": "to", "pattern": "ops"}}, {"arg": {"tool": "write", "name": "key", "pattern": "report:*"}})
    s, r = run(lambda t, w: CapabilityTools(t, SECRET, cap, w.clock))
    m = metrics(s, r)
    assert m["success"] and not m["exfiltrated"] and s.tools.denials == 1
    assert [x.name for x in CapabilityTools(s.tools, SECRET, attenuate(cap, {"tools": ["lookup"]})).specs()] == ["lookup"]
