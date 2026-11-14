"""Execution tracing: one event stream, three consumers.

1. Flat event log  -> `Tracer.events`, `write_jsonl`
2. Span tree       -> `build_spans` (OpenTelemetry-shaped, GenAI attribute names)
3. Record/replay   -> `Tape`, `ReplayModel`, `ReplayTools`
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .types import ModelRequest, ModelResponse, ToolCall, ToolResult, ToolSpec
from .util import SimClock, decode, encode, fingerprint


class Tracer:
    def __init__(self, clock: SimClock | None = None, enabled: bool = True):
        self.clock = clock or SimClock()
        self.enabled = enabled
        self.events: list[dict[str, Any]] = []
        self._stack: list[str] = []
        self._spans = 0

    def emit(self, kind: str, agent: str = "", **data: Any) -> None:
        if not self.enabled:
            return
        self.events.append(
            {
                "seq": len(self.events),
                "t_ms": self.clock.now_ms,
                "kind": kind,
                "agent": agent,
                "span": self._stack[-1] if self._stack else "",
                "data": encode(data),
            }
        )

    @contextmanager
    def span(self, name: str, agent: str = "", **attrs: Any) -> Iterator[str]:
        if not self.enabled:
            yield ""
            return
        self._spans += 1
        sid = f"sp{self._spans}"
        parent = self._stack[-1] if self._stack else ""
        self._stack.append(sid)
        self.emit("span_start", agent, name=name, parent=parent, **attrs)
        status = "ok"
        try:
            yield sid
        except BaseException as exc:
            status = type(exc).__name__
            raise
        finally:
            self.emit("span_end", agent, status=status)
            self._stack.pop()

    def write_jsonl(self, path: str | Path) -> None:
        Path(path).write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in self.events))


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


_OP = {"model_call": "chat", "tool_result": "execute_tool"}


def build_spans(events: list[dict[str, Any]], trace_id: str = "trace-0") -> list[dict[str, Any]]:
    """Fold the event stream into spans shaped like OpenTelemetry's data model.

    Attribute names follow the OpenTelemetry GenAI semantic conventions
    (`gen_ai.operation.name`, `gen_ai.usage.input_tokens`, ...). Model and tool
    calls become leaf spans under the enclosing explicit span.
    """
    spans: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    leaf = 0
    for e in events:
        d = e["data"]
        if e["kind"] == "span_start":
            spans[e["span"]] = {
                "trace_id": trace_id,
                "span_id": e["span"],
                "parent_span_id": d.get("parent", ""),
                "name": d["name"],
                "start_ms": e["t_ms"],
                "end_ms": e["t_ms"],
                "status": "unset",
                "attributes": {"gen_ai.agent.name": e["agent"], **{k: v for k, v in d.items() if k not in ("name", "parent")}},
            }
            out.append(spans[e["span"]])
        elif e["kind"] == "span_end":
            spans[e["span"]]["end_ms"] = e["t_ms"]
            spans[e["span"]]["status"] = d["status"]
        elif e["kind"] in _OP:
            leaf += 1
            attrs: dict[str, Any] = {"gen_ai.operation.name": _OP[e["kind"]], "gen_ai.agent.name": e["agent"]}
            if e["kind"] == "model_call":
                r = d["response"]
                attrs.update(
                    {
                        "gen_ai.request.model": r["model"],
                        "gen_ai.usage.input_tokens": r["prompt_tokens"],
                        "gen_ai.usage.output_tokens": r["completion_tokens"],
                        "agentlab.mode": d["mode"],
                    }
                )
                name, dur, ok = f"chat {r['model']}", r["latency_ms"], True
            else:
                attrs["gen_ai.tool.name"] = d["call"]["tool"]
                name, dur, ok = f"execute_tool {d['call']['tool']}", d.get("duration_ms", 0), d["result"]["ok"]
                if not ok:
                    attrs["error.type"] = d["result"]["error_code"]
            out.append(
                {
                    "trace_id": trace_id,
                    "span_id": f"leaf{leaf}",
                    "parent_span_id": e["span"],
                    "name": name,
                    "start_ms": e["t_ms"] - dur,
                    "end_ms": e["t_ms"],
                    "status": "ok" if ok else "error",
                    "attributes": attrs,
                }
            )
    return out


class ReplayDivergence(RuntimeError):
    """The code under replay asked for something the recording does not contain."""


class Tape:
    """Recorded model responses and tool results, in order, keyed by request fingerprint."""

    def __init__(self, events: list[dict[str, Any]]):
        self.model = [(e["data"]["request_fp"], e["data"]["response"]) for e in events if e["kind"] == "model_call"]
        self.tools = [(fingerprint_call(decode(e["data"]["call"])), e["data"]["result"], e["data"].get("duration_ms", 0)) for e in events if e["kind"] == "tool_result"]


def fingerprint_request(req: ModelRequest) -> str:
    return fingerprint([req.mode, req.messages, [t.name for t in req.tools], req.params])


def fingerprint_call(call: ToolCall) -> str:
    return fingerprint([call.tool, call.args, call.step_id])


class ReplayModel:
    """Serves recorded responses; raises if the replayed code diverges from the recording."""

    def __init__(self, tape: Tape):
        self._items = list(tape.model)
        self._i = 0

    def complete(self, req: ModelRequest) -> ModelResponse:
        if self._i >= len(self._items):
            raise ReplayDivergence("model called more times than recorded")
        fp, resp = self._items[self._i]
        if fp != fingerprint_request(req):
            raise ReplayDivergence(f"model request #{self._i} differs from recording")
        self._i += 1
        return decode(resp)


class ReplayTools:
    def __init__(self, tape: Tape, specs: list[ToolSpec], clock: SimClock | None = None):
        self._items = list(tape.tools)
        self._specs = specs
        self._clock = clock
        self._i = 0

    def specs(self) -> list[ToolSpec]:
        return self._specs

    def execute(self, call: ToolCall) -> ToolResult:
        if self._i >= len(self._items):
            raise ReplayDivergence("tool called more times than recorded")
        fp, result, duration = self._items[self._i]
        if fp != fingerprint_call(call):
            raise ReplayDivergence(f"tool call #{self._i} differs from recording")
        self._i += 1
        if self._clock is not None:
            self._clock.advance(duration)
        return decode(result)
