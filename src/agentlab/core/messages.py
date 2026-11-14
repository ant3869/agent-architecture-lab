"""Message constructors. `meta` is the structured channel; `content` is what gets tokenised.

A real model reads `content`. The simulator reads `meta` so that what the model
"knows" is exactly what is visible in its context window and nothing else.
"""
from __future__ import annotations

import json
from typing import Any

from .types import Message, ModelResponse, ToolCall, ToolResult
from .util import encode


def assistant_message(resp: ModelResponse) -> Message:
    meta: dict[str, Any] = {}
    if resp.call is not None:
        meta["call"] = encode(resp.call)
    if resp.plan is not None:
        meta["plan"] = encode(resp.plan)
    if resp.final:
        meta["final"] = True
    if resp.data.get("toward"):
        meta["toward"] = resp.data["toward"]
    return Message("assistant", resp.text, meta)


def tool_message(call: ToolCall, result: ToolResult) -> Message:
    if result.ok:
        body = json.dumps(result.output)
        if result.note:
            body += f" | {result.note}"
    else:
        body = f"ERROR {result.error_code}: {result.error}"
    return Message(
        "tool",
        f"Observation[{call.step_id}] {call.tool} -> {body}",
        {
            "step_id": call.step_id,
            "tool": call.tool,
            "args": dict(call.args),
            "ok": result.ok,
            "output": result.output,
            "error_code": result.error_code,
            "info": dict(result.info),
        },
    )


def memory_message(facts: dict[str, Any], done: list[str], moved: dict[str, str], attempts: dict[str, int] | None = None) -> Message:
    parts = [f"{k}={json.dumps(v)}" for k, v in facts.items()]
    text = "Memory: completed " + (", ".join(done) or "nothing") + ". Known values: " + (", ".join(parts) or "none") + "."
    if moved:
        text += " Relocated keys: " + ", ".join(f"{a}->{b}" for a, b in moved.items()) + "."
    return Message("memory", text, {"facts": dict(facts), "done": list(done), "moved": dict(moved), "attempts": dict(attempts or {})})


def verdict_message(invalid: list[str], reason: str = "verifier") -> Message:
    return Message("system", f"Verifier rejected: {', '.join(invalid)}. Redo these steps.", {"invalid": list(invalid), "reason": reason})


def rejection_message(call: ToolCall) -> Message:
    """A proposed (not executed) call was rejected before reaching the backend."""
    return tool_message(call, ToolResult(False, error_code="REJECTED_BY_VERIFIER", error="proposed call failed pre-execution verification"))
