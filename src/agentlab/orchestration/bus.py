"""In-process message bus with agent discovery.

The envelope and card shapes are inspired by the A2A protocol (agent cards advertise
skills; work is exchanged as task messages with a lifecycle) but this is not an A2A
implementation: there is no HTTP binding, no auth and no streaming.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.trace import Tracer
from ..core.util import SimClock, estimate_tokens

TASK_STATES = ("submitted", "working", "completed", "failed", "canceled")


@dataclass(frozen=True)
class AgentCard:
    name: str
    skills: tuple[str, ...]
    description: str = ""


@dataclass
class Envelope:
    sender: str
    recipient: str
    kind: str  # task | result | handoff | status
    task_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    seq: int = 0
    ts_ms: int = 0

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


class AgentUnavailable(RuntimeError):
    pass


class MessageBus:
    def __init__(self, clock: SimClock | None = None, tracer: Tracer | None = None):
        self.clock = clock or SimClock()
        self.tracer = tracer or Tracer(self.clock, enabled=False)
        self.cards: dict[str, AgentCard] = {}
        self.down: set[str] = set()
        self.log: list[Envelope] = []

    def register(self, card: AgentCard) -> None:
        if card.name in self.cards:
            raise ValueError(f"agent already registered: {card.name}")
        self.cards[card.name] = card

    def mark_down(self, name: str) -> None:
        self.down.add(name)

    def resolve(self, skill: str) -> list[str]:
        """Live agents advertising `skill`, in registration order."""
        return [n for n, c in self.cards.items() if skill in c.skills and n not in self.down]

    def send(self, env: Envelope) -> Envelope:
        if env.recipient not in self.cards:
            raise AgentUnavailable(f"unknown agent: {env.recipient}")
        if env.recipient in self.down:
            raise AgentUnavailable(f"agent is down: {env.recipient}")
        env.seq, env.ts_ms = len(self.log), self.clock.now_ms
        self.log.append(env)
        self.tracer.emit("message", env.sender, to=env.recipient, msg_kind=env.kind, task_id=env.task_id, tokens=env.tokens, text=env.text)
        return env

    @property
    def message_tokens(self) -> int:
        return sum(e.tokens for e in self.log)
