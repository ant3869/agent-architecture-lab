"""Model routing: pick which model serves each request.

`RoutedModel` is itself a `Model`, so any loop can use any router without changes.
"""
from __future__ import annotations

from typing import Protocol

from ..core.types import Model, ModelRequest, ModelResponse


class Router(Protocol):
    name: str

    def choose(self, req: ModelRequest) -> str: ...


class StaticRouter:
    """Always the same model. The baseline every other router must beat."""

    def __init__(self, model: str):
        self.model = model
        self.name = f"static:{model}"

    def choose(self, req: ModelRequest) -> str:
        return self.model


class RoleRouter:
    """Route by the role of the call: strong model for rare, high-leverage calls
    (planning, verification), cheap model for the frequent ones."""

    name = "role"

    def __init__(self, strong: str, cheap: str, strong_modes: tuple[str, ...] = ("plan", "replan", "verify", "decompose")):
        self.strong, self.cheap, self.strong_modes = strong, cheap, strong_modes

    def choose(self, req: ModelRequest) -> str:
        return self.strong if req.mode in self.strong_modes else self.cheap


class CascadeRouter:
    """Start cheap, escalate on evidence of failure.

    Evidence is read from the request itself: the most recent message is a failed tool
    result or a verifier rejection. Verification is always done by the strong model,
    because a cascade is only as good as its failure detector (FrugalGPT, arXiv:2305.05176).
    """

    name = "cascade"

    def __init__(self, strong: str, cheap: str, strong_modes: tuple[str, ...] = ("verify",)):
        self.strong, self.cheap, self.strong_modes = strong, cheap, strong_modes
        self.escalations = 0

    def choose(self, req: ModelRequest) -> str:
        if req.mode in self.strong_modes:
            return self.strong
        last = req.messages[-1] if req.messages else None
        failed = last is not None and ((last.role == "tool" and last.meta.get("ok") is False) or bool(last.meta.get("invalid")))
        if failed:
            self.escalations += 1
            return self.strong
        return self.cheap


class RoutedModel:
    def __init__(self, models: dict[str, Model], router: Router):
        self.models, self.router = models, router

    def complete(self, req: ModelRequest) -> ModelResponse:
        return self.models[self.router.choose(req)].complete(req)
