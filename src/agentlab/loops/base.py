"""Common result type and helpers for execution loops."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.types import Message, ToolCall


@dataclass
class LoopResult:
    status: str  # final | blocked | max_iters | failed | interrupted
    iterations: int = 0  # tool executions driven by the loop
    replans: int = 0
    repairs: int = 0
    history: list[Message] = field(default_factory=list)
    pending: ToolCall | None = None  # set when status == "interrupted"
    detail: str = ""


def resolve_refs(call: ToolCall, results: dict[str, Any]) -> ToolCall | None:
    """Substitute `{"$ref": step}` placeholders. Returns None when a referenced value is unavailable."""
    args: dict[str, Any] = {}
    for k, v in call.args.items():
        if isinstance(v, dict) and "$ref" in v:
            if v["$ref"] not in results:
                return None
            args[k] = results[v["$ref"]]
        else:
            args[k] = v
    return ToolCall(call.tool, args, call.step_id, call.idem_key)


def plan_refs(call: ToolCall) -> list[str]:
    return [v["$ref"] for v in call.args.values() if isinstance(v, dict) and "$ref" in v]
