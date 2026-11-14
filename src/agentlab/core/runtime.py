"""Runtime: the single choke point through which loops reach models and tools.

Every architecture calls `call_model` / `call_tool` here, so metering and tracing
are identical across architectures and comparisons stay apples-to-apples.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .trace import Tracer, fingerprint_request
from .types import Message, Model, ModelRequest, ModelResponse, ToolCall, ToolExecutor, ToolResult, ToolSpec
from .util import SimClock


@dataclass
class Meter:
    model_calls: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    peak_prompt_tokens: int = 0
    cost: float = 0.0
    replayed_model_calls: int = 0
    replayed_tool_calls: int = 0
    by_model: dict[str, int] = field(default_factory=dict)
    by_mode: dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Runtime:
    def __init__(
        self,
        model: Model,
        tools: ToolExecutor,
        *,
        clock: SimClock | None = None,
        tracer: Tracer | None = None,
        meter: Meter | None = None,
        agent: str = "agent",
    ):
        self.model = model
        self.tools = tools
        self.clock = clock or SimClock()
        self.tracer = tracer or Tracer(self.clock, enabled=False)
        self.meter = meter or Meter()
        self.agent = agent

    def call_model(self, mode: str, messages: list[Message], tools: list[ToolSpec] | None = None, **params: Any) -> ModelResponse:
        req = ModelRequest(mode, list(messages), self.tools.specs() if tools is None else tools, params)
        resp = self.model.complete(req)
        m = self.meter
        if resp.replayed:
            m.replayed_model_calls += 1
        else:
            self.clock.advance(resp.latency_ms)
            m.model_calls += 1
            m.prompt_tokens += resp.prompt_tokens
            m.completion_tokens += resp.completion_tokens
            m.peak_prompt_tokens = max(m.peak_prompt_tokens, resp.prompt_tokens)
            m.cost += resp.cost
            m.by_model[resp.model] = m.by_model.get(resp.model, 0) + 1
            m.by_mode[mode] = m.by_mode.get(mode, 0) + 1
        if self.tracer.enabled:
            self.tracer.emit("model_call", self.agent, mode=mode, request_fp=fingerprint_request(req), response=resp)
        return resp

    def call_tool(self, call: ToolCall) -> ToolResult:
        t0 = self.clock.now_ms
        result = self.tools.execute(call)
        if result.replayed:
            self.meter.replayed_tool_calls += 1
        else:
            self.meter.tool_calls += 1
        if self.tracer.enabled:
            self.tracer.emit("tool_result", self.agent, call=call, result=result, duration_ms=self.clock.now_ms - t0)
        return result
