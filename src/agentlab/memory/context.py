"""Context policies: what part of the history the model sees on each call.

All policies keep the full history as the system of record; they differ only in the
*view* handed to the model. Message 0 (the goal) is always pinned.
"""
from __future__ import annotations

from typing import Any, Protocol

from ..core.messages import memory_message
from ..core.runtime import Runtime
from ..core.types import Message
from ..core.util import estimate_tokens


class ContextPolicy(Protocol):
    name: str

    def view(self, history: list[Message], rt: Runtime) -> list[Message]: ...


def tokens(messages: list[Message]) -> int:
    return sum(estimate_tokens(m.content) for m in messages)


class FullHistory:
    name = "full"

    def view(self, history: list[Message], rt: Runtime) -> list[Message]:
        return history


class SlidingWindow:
    """Goal + the last `n` messages. Cheap, lossy, no extra model calls."""

    def __init__(self, n: int = 8):
        if n < 2:
            raise ValueError("window must hold at least one action/observation pair")
        self.n = n
        self.name = f"window-{n}"

    def view(self, history: list[Message], rt: Runtime) -> list[Message]:
        if len(history) <= self.n + 1:
            return history
        return [history[0]] + history[-self.n :]


class Compaction:
    """When the view beyond the pinned goal exceeds `max_tokens`, summarise everything but the
    last `keep_recent` messages with a model call and continue from the summary."""

    def __init__(self, max_tokens: int = 600, keep_recent: int = 4):
        self.max_tokens, self.keep_recent = max_tokens, keep_recent
        self.name = f"compaction-{max_tokens}"
        self._summary: Message | None = None
        self._cut = 1  # history[1:_cut] is covered by the summary
        self.compactions = 0

    def _assemble(self, history: list[Message]) -> list[Message]:
        head = [history[0]] + ([self._summary] if self._summary else [])
        return head + history[self._cut :]

    def view(self, history: list[Message], rt: Runtime) -> list[Message]:
        current = self._assemble(history)
        new_cut = len(history) - self.keep_recent
        if tokens(current[1:]) <= self.max_tokens or new_cut <= self._cut:
            return current
        chunk = [history[0]] + ([self._summary] if self._summary else []) + history[self._cut : new_cut]
        resp = rt.call_model("summarize", chunk, tools=[])
        d = resp.data
        self._summary = memory_message(d["facts"], d["done"], d["moved"], d["attempts"])
        self._cut = new_cut
        self.compactions += 1
        return self._assemble(history)


class FactLedger:
    """Structured note-taking: the runtime copies each tool result into a keyed ledger
    (no model call) and shows the model the ledger plus the last `keep_recent` messages."""

    def __init__(self, keep_recent: int = 2):
        self.keep_recent = keep_recent
        self.name = "ledger"
        self._facts: dict[str, Any] = {}
        self._done: list[str] = []
        self._moved: dict[str, str] = {}
        self._seen = 1

    def _absorb(self, history: list[Message]) -> None:
        for m in history[self._seen :]:
            meta = m.meta
            for sid in meta.get("invalid", ()):
                self._facts.pop(sid, None)
                if sid in self._done:
                    self._done.remove(sid)
            if m.role == "tool" and "step_id" in meta:
                sid = meta["step_id"]
                if meta["ok"] and not sid.startswith("_"):
                    self._facts[sid] = meta["output"]
                    if sid not in self._done:
                        self._done.append(sid)
                elif meta["error_code"] == "MOVED":
                    self._moved[meta["args"]["key"]] = meta["info"]["moved_to"]
        self._seen = len(history)

    def view(self, history: list[Message], rt: Runtime) -> list[Message]:
        self._absorb(history)
        if len(history) <= self.keep_recent + 1:
            return history
        return [history[0], memory_message(self._facts, self._done, self._moved)] + history[-self.keep_recent :]
