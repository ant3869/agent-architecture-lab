"""Deterministic primitives: hashing RNG, token estimate, simulated clock, JSON codec."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

from . import types as _t


def u01(*parts: Any) -> float:
    """Uniform [0,1) drawn from a stable hash of `parts`.

    Unlike `random`, the draw depends only on its key, never on call order, so two
    architectures given the same seed face the same faults (common random numbers).
    """
    h = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2**64


def estimate_tokens(text: str) -> int:
    """~4 characters per token. A fixed, documented proxy; not a real tokenizer."""
    return max(1, (len(text) + 3) // 4)


class SimClock:
    """Virtual time in milliseconds. Nothing in the lab ever sleeps."""

    def __init__(self, now_ms: int = 0):
        self.now_ms = now_ms

    def advance(self, ms: float) -> None:
        if ms < 0:
            raise ValueError("time cannot go backwards")
        self.now_ms += int(round(ms))


_TYPES = {
    c.__name__: c
    for c in (_t.ToolSpec, _t.ToolCall, _t.ToolResult, _t.Message, _t.ModelResponse, _t.ModelRequest)
}


def encode(obj: Any) -> Any:
    """Dataclasses -> tagged JSON-able dicts (lossless for the types in `_TYPES`)."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {"__t": type(obj).__name__}
        for f in dataclasses.fields(obj):
            out[f.name] = encode(getattr(obj, f.name))
        return out
    if isinstance(obj, dict):
        return {str(k): encode(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [encode(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(encode(v) for v in obj)
    return obj


def decode(obj: Any) -> Any:
    if isinstance(obj, dict):
        if "__t" in obj:
            cls = _TYPES[obj["__t"]]
            return cls(**{k: decode(v) for k, v in obj.items() if k != "__t"})
        return {k: decode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decode(v) for v in obj]
    return obj


def dumps(obj: Any) -> str:
    return json.dumps(encode(obj), sort_keys=True, separators=(",", ":"))


def loads(text: str) -> Any:
    return decode(json.loads(text))


def fingerprint(obj: Any) -> str:
    return hashlib.blake2b(dumps(obj).encode(), digest_size=8).hexdigest()
