"""Event-sourced durable execution: journal every nondeterministic result, recover by replay.

The agent code is re-run from the top after a crash. `DurableSession` intercepts each
model call and tool call; if the journal already holds its result the recorded value is
returned and nothing external happens. Execution "catches up" to the crash point and
continues live. This is the Temporal / Restate / DBOS model, and it needs one thing
from the agent code: determinism given the same recorded results.
"""
from __future__ import annotations

from dataclasses import replace

from ..core.trace import fingerprint_call, fingerprint_request
from ..core.types import Model, ModelRequest, ModelResponse, ToolCall, ToolExecutor, ToolResult, ToolSpec
from .stores import SQLiteJournal


class NonDeterminismError(RuntimeError):
    """On replay the code asked for something different from what the journal recorded."""


class DurableSession:
    def __init__(self, journal: SQLiteJournal, run_id: str, idempotency_keys: bool = True):
        self.journal = journal
        self.run_id = run_id
        self.idempotency_keys = idempotency_keys
        self._log = journal.load(run_id)
        self._pos = 0
        self.replayed = 0

    def _recorded(self, kind: str, fp: str) -> dict | None:
        if self._pos >= len(self._log):
            return None
        rec = self._log[self._pos]
        if rec["kind"] != kind or rec["fp"] != fp:
            raise NonDeterminismError(f"journal position {self._pos}: recorded {rec['kind']}/{rec['fp']}, code produced {kind}/{fp}")
        self._pos += 1
        return rec

    def _append(self, kind: str, fp: str, payload: object) -> None:
        self.journal.append(self.run_id, kind, fp, payload)
        self._log.append({"kind": kind, "fp": fp, "payload": payload})
        self._pos += 1

    def model(self, inner: Model) -> "JournaledModel":
        return JournaledModel(self, inner)

    def tools(self, inner: ToolExecutor) -> "JournaledTools":
        return JournaledTools(self, inner)


class JournaledModel:
    def __init__(self, session: DurableSession, inner: Model):
        self.s, self.inner = session, inner

    def complete(self, req: ModelRequest) -> ModelResponse:
        fp = fingerprint_request(req)
        rec = self.s._recorded("model", fp)
        if rec is not None:
            self.s.replayed += 1
            return replace(rec["payload"], replayed=True)
        resp = self.inner.complete(req)
        self.s._append("model", fp, resp)
        return resp


class JournaledTools:
    """Write-ahead: record the intent, execute with a journal-derived idempotency key, record the result.

    A crash between effect and result leaves an intent without a result. On recovery the
    call is re-issued under the *same* key, so a backend that honours idempotency keys
    applies the effect exactly once.
    """

    def __init__(self, session: DurableSession, inner: ToolExecutor):
        self.s, self.inner = session, inner

    def specs(self) -> list[ToolSpec]:
        return self.inner.specs()

    def execute(self, call: ToolCall) -> ToolResult:
        fp = fingerprint_call(call)
        intent_pos = self.s._pos
        if self.s._recorded("intent", fp) is None:
            self.s._append("intent", fp, call)
        rec = self.s._recorded("result", fp)
        if rec is not None:
            self.s.replayed += 1
            return replace(rec["payload"], replayed=True)
        keyed = replace(call, idem_key=f"{self.s.run_id}:{intent_pos}") if self.s.idempotency_keys else call
        result = self.inner.execute(keyed)
        self.s._append("result", fp, result)
        return result
