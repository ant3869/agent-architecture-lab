"""Shared value types and the two protocols every architecture is written against.

`Model` and `ToolExecutor` are the only seams between an architecture and the
outside world. The simulator implements both deterministically; real adapters
(see `integrations/`) implement the same protocols.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    params: dict[str, str]  # arg name -> "string" | "number" | "any"
    effect: str = "read"  # read | write | external  (risk tier)
    idempotent: bool = True
    domain: str = "general"
    constraints: dict[str, dict[str, Any]] = field(default_factory=dict)  # arg -> {"enum": [...]} | {"pattern": regex}

    def render(self) -> str:
        """Text shown to the model. Its length is charged as prompt tokens."""
        sig = ", ".join(f"{k}: {t}" for k, t in self.params.items())
        return f"{self.name}({sig}) - {self.description} [effect={self.effect}]"

    def json_schema(self) -> dict[str, Any]:
        types = {"string": {"type": "string"}, "number": {"type": "number"}, "any": {}}
        return {
            "type": "object",
            "properties": {k: {**types.get(t, {}), **self.constraints.get(k, {})} for k, t in self.params.items()},
            "required": list(self.params),
            "additionalProperties": False,
        }


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict[str, Any]
    step_id: str = ""  # the model's stated intent: which sub-goal this call serves
    idem_key: str = ""  # idempotency key, set by the runtime (never by the model)


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: Any = None
    error_code: str = ""
    error: str = ""
    retryable: bool = False
    note: str = ""  # untrusted free text returned by the data source
    info: dict[str, Any] = field(default_factory=dict)
    attempts: int = 1  # backend attempts made by runtime retry layers
    deduped: bool = False  # served from an idempotency record, no new effect
    replayed: bool = False  # served from a journal/tape, backend not touched


@dataclass
class Message:
    role: str  # system | user | assistant | tool | memory
    content: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelRequest:
    mode: str  # act | plan | replan | verify | finalize | decompose | summarize
    messages: list[Message]
    tools: list[ToolSpec]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    text: str
    call: ToolCall | None = None
    plan: list[ToolCall] | None = None
    data: dict[str, Any] = field(default_factory=dict)
    final: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    latency_ms: int = 0
    cost: float = 0.0
    replayed: bool = False


@runtime_checkable
class Model(Protocol):
    def complete(self, req: ModelRequest) -> ModelResponse: ...


@runtime_checkable
class ToolExecutor(Protocol):
    def specs(self) -> list[ToolSpec]:
        """Tools currently exposed to the model."""
        ...

    def execute(self, call: ToolCall) -> ToolResult: ...


class SimulatedCrash(BaseException):
    """Process death. Derives from BaseException so no `except Exception` swallows it."""


class Interrupt(Exception):
    """Raised by a tool layer or graph node to pause a run for external input."""

    def __init__(self, payload: dict[str, Any]):
        super().__init__(payload.get("reason", "interrupt"))
        self.payload = payload
