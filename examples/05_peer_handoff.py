"""Peer-to-peer handoff: agents pass the conversation to each other; no coordinator.

Shows multi-agent communication over the message bus: every handoff is an envelope
that carries the full transcript to the next specialist.

Run:  python examples/05_peer_handoff.py
"""
from agentlab.core.runtime import Meter
from agentlab.core.util import SimClock
from agentlab.orchestration.handoff import HandoffSwarm
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import world_tools

task = make_task(seed=5, stages=2, lookups=2)
clock = SimClock()
world, meter = World(task, clock), Meter()

swarm = HandoffSwarm(SimModel(ModelProfile(), task), world_tools(world), clock=clock, meter=meter)
res = swarm.run(task)

print("agents:", {name: card.skills for name, card in swarm.bus.cards.items()})
for env in swarm.bus.log:
    print(f"  #{env.seq} t={env.ts_ms:>6}ms {env.sender:7} -> {env.recipient:7} {env.kind} ({env.payload['messages']} messages, {env.tokens} tokens)")
print(f"\nstatus={res.status} handoffs={res.handoffs} model_calls={meter.model_calls} tokens={meter.total_tokens} peak_context={meter.peak_prompt_tokens}")
print("goal check:", evaluate(task, world))
