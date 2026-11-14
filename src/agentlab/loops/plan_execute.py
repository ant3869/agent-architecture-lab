"""Plan-and-Execute with symbolic variables and replan-on-failure.

One model call writes the whole plan; later steps reference earlier results by name
(`{"$ref": "s2"}`) so the executor can run them without consulting the model.
Lineage: Plan-and-Solve (arXiv:2305.04091), ReWOO (arXiv:2305.18323), LLMCompiler
(arXiv:2312.04511). The model is called again only when a step fails, and once to finish.
"""
from __future__ import annotations

from typing import Any

from ..core.messages import assistant_message, tool_message
from ..core.runtime import Runtime
from ..core.types import Message, ToolCall, ToolResult
from ..memory.context import ContextPolicy, FullHistory
from .base import LoopResult, resolve_refs


class PlanExecuteLoop:
    name = "plan_execute"

    def __init__(self, rt: Runtime, memory: ContextPolicy | None = None, max_replans: int = 12, max_iters: int = 200):
        self.rt = rt
        self.memory = memory or FullHistory()
        self.max_replans = max_replans
        self.max_iters = max_iters

    def run(self, goal: Message) -> LoopResult:
        history: list[Message] = [goal]
        results: dict[str, Any] = {}
        replans = iters = 0
        with self.rt.tracer.span("plan_execute.run", self.rt.agent):
            plan = self._plan("plan", history)
            cursor = 0
            while cursor < len(plan):
                if iters >= self.max_iters:
                    return LoopResult("max_iters", iters, replans, history=history)
                call = resolve_refs(plan[cursor], results)
                if call is None:
                    result = ToolResult(False, error_code="UNRESOLVED_REF", error="plan references a value that was never produced")
                    call = plan[cursor]
                else:
                    result = self.rt.call_tool(call)
                    iters += 1
                history.append(tool_message(call, result))
                if result.ok:
                    results[call.step_id] = result.output
                    cursor += 1
                    continue
                if replans >= self.max_replans:
                    return LoopResult("failed", iters, replans, history=history, detail=f"replan budget exhausted at {call.step_id}")
                replans += 1
                plan, cursor = self._plan("replan", history), 0
            resp = self.rt.call_model("finalize", self.memory.view(history, self.rt))
            history.append(assistant_message(resp))
            return LoopResult("final", iters, replans, history=history, detail=resp.text)

    def _plan(self, mode: str, history: list[Message]) -> list[ToolCall]:
        resp = self.rt.call_model(mode, self.memory.view(history, self.rt))
        history.append(assistant_message(resp))
        return list(resp.plan or [])
