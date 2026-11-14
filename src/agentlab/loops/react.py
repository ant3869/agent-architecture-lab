"""ReAct: interleave one model call with one tool call until the model says it is done.

Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (arXiv:2210.03629).
The model sees every observation before choosing the next action, so it adapts to
surprises for free and pays for that with one model call per step over a growing context.
"""
from __future__ import annotations

from typing import Callable

from ..core.messages import assistant_message, tool_message
from ..core.runtime import Runtime
from ..core.types import Interrupt, Message, ToolCall, ToolResult
from ..memory.context import ContextPolicy, FullHistory
from .base import LoopResult


class ReActLoop:
    name = "react"

    def __init__(
        self,
        rt: Runtime,
        memory: ContextPolicy | None = None,
        max_iters: int = 80,
        on_step: Callable[[list[Message]], None] | None = None,
    ):
        self.rt = rt
        self.memory = memory or FullHistory()
        self.max_iters = max_iters
        self.on_step = on_step  # called after each completed iteration: the checkpoint hook

    def run(
        self,
        goal: Message,
        resume: list[Message] | None = None,
        pending: tuple[ToolCall, bool] | None = None,
    ) -> LoopResult:
        """Run to completion.

        `resume` continues from a saved history. `pending=(call, approved)` settles a call
        that previously raised `Interrupt` (human-in-the-loop approval).
        """
        history = list(resume) if resume else [goal]
        iters = 0
        with self.rt.tracer.span("react.run", self.rt.agent):
            if pending is not None:
                call, approved = pending
                self._settle(history, call, approved)
                iters += 1
            while iters < self.max_iters:
                resp = self.rt.call_model("act", self.memory.view(history, self.rt))
                if resp.final:
                    history.append(assistant_message(resp))
                    return LoopResult("blocked" if resp.data.get("blocked") else "final", iters, history=history, detail=resp.text)
                assert resp.call is not None
                history.append(assistant_message(resp))
                try:
                    result = self.rt.call_tool(resp.call)
                except Interrupt:
                    return LoopResult("interrupted", iters, history=history, pending=resp.call)
                history.append(tool_message(resp.call, result))
                iters += 1
                if self.on_step:
                    self.on_step(history)
            return LoopResult("max_iters", iters, history=history)

    def _settle(self, history: list[Message], call: ToolCall, approved: bool) -> None:
        if approved:
            result = self.rt.call_tool(call)
        else:
            result = ToolResult(False, error_code="APPROVAL_DENIED", error="a human reviewer denied this action")
        history.append(tool_message(call, result))
        if self.on_step:
            self.on_step(history)
