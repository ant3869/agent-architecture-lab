"""Durable stores on SQLite (stdlib). `:memory:` for experiments, a file path for real durability."""
from __future__ import annotations

import sqlite3
from typing import Any

from ..core.util import dumps, loads


class SQLiteCheckpointer:
    """Snapshot store: one full-state row per checkpoint, addressed by thread id."""

    def __init__(self, path: str = ":memory:"):
        self._db = sqlite3.connect(path)
        self._db.execute("CREATE TABLE IF NOT EXISTS checkpoints (thread TEXT, seq INTEGER, payload TEXT, PRIMARY KEY (thread, seq))")
        self._db.commit()
        self.bytes_written = 0
        self.writes = 0

    def put(self, thread_id: str, payload: dict[str, Any]) -> int:
        text = dumps(payload)
        (seq,) = self._db.execute("SELECT COALESCE(MAX(seq), -1) + 1 FROM checkpoints WHERE thread = ?", (thread_id,)).fetchone()
        self._db.execute("INSERT INTO checkpoints VALUES (?, ?, ?)", (thread_id, seq, text))
        self._db.commit()
        self.bytes_written += len(text)
        self.writes += 1
        return seq

    def latest(self, thread_id: str) -> dict[str, Any] | None:
        row = self._db.execute("SELECT payload FROM checkpoints WHERE thread = ? ORDER BY seq DESC LIMIT 1", (thread_id,)).fetchone()
        return loads(row[0]) if row else None

    def history(self, thread_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT payload FROM checkpoints WHERE thread = ? ORDER BY seq", (thread_id,)).fetchall()
        return [loads(r[0]) for r in rows]

    def close(self) -> None:
        self._db.close()


class SQLiteJournal:
    """Append-only event journal: one small row per nondeterministic result."""

    def __init__(self, path: str = ":memory:"):
        self._db = sqlite3.connect(path)
        self._db.execute("CREATE TABLE IF NOT EXISTS journal (run TEXT, seq INTEGER, kind TEXT, fp TEXT, payload TEXT, PRIMARY KEY (run, seq))")
        self._db.commit()
        self.bytes_written = 0
        self.writes = 0

    def append(self, run_id: str, kind: str, fp: str, payload: Any) -> int:
        text = dumps(payload)
        (seq,) = self._db.execute("SELECT COALESCE(MAX(seq), -1) + 1 FROM journal WHERE run = ?", (run_id,)).fetchone()
        self._db.execute("INSERT INTO journal VALUES (?, ?, ?, ?, ?)", (run_id, seq, kind, fp, text))
        self._db.commit()
        self.bytes_written += len(text) + len(fp) + len(kind)
        self.writes += 1
        return seq

    def load(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT seq, kind, fp, payload FROM journal WHERE run = ? ORDER BY seq", (run_id,)).fetchall()
        return [{"seq": s, "kind": k, "fp": f, "payload": loads(p)} for s, k, f, p in rows]

    def close(self) -> None:
        self._db.close()
