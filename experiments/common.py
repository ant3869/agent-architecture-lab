"""Shared helpers for experiments. Every experiment module exposes `run(n) -> dict`."""
from __future__ import annotations

from typing import Any, Callable, Iterable

from agentlab.eval.harness import aggregate


def cell(labels: dict[str, Any], rows: Iterable[dict[str, Any]], extra: Iterable[str] = ()) -> dict[str, Any]:
    return {**labels, **aggregate(rows, extra)}


def find(rows: list[dict[str, Any]], **labels: Any) -> dict[str, Any]:
    for r in rows:
        if all(r.get(k) == v for k, v in labels.items()):
            return r
    raise KeyError(labels)


def pct(a: float, b: float) -> str:
    """Relative change of a versus b, as a signed percentage string."""
    return "n/a" if b == 0 else f"{(a - b) / b * 100:+.0f}%"


def ratio(a: float, b: float) -> str:
    return "n/a" if b == 0 else f"{a / b:.1f}x"


def experiment(id: str, title: str, question: str, conditions: dict[str, Any], columns: list[tuple[str, str]], group_by: list[str], rows: list[dict[str, Any]], findings: list[str], limitations: list[str]) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "question": question,
        "conditions": conditions,
        "columns": [{"key": k, "label": lab} for k, lab in columns],
        "group_by": group_by,
        "rows": rows,
        "findings": findings,
        "limitations": limitations,
    }
