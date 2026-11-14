"""Permissions: allowlist, human approval with interrupt/resume, and attenuated capability tokens.

The looked-up record contains an injected instruction to send data to an outside recipient,
and the simulated model always obeys it.

Run:  python examples/13_permissions_and_approval.py
"""
from agentlab.core.runtime import Runtime
from agentlab.loops.react import ReActLoop
from agentlab.permissions.policy import AllowlistTools, ApprovalTools, CapabilityTools, attenuate, mint, verify_signature
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import World
from agentlab.tools.registry import StaticRegistry, world_tools

task = make_task(seed=1, stages=1, lookups=3, poisoned=True)
gullible = ModelProfile(injection_susceptibility=1.0)


def fresh(wrap):
    world = World(task)
    tools = wrap(StaticRegistry(world_tools(world)), world)
    return world, tools, Runtime(SimModel(gullible, task), tools, clock=world.clock)


world, _, rt = fresh(lambda t, w: AllowlistTools(t, {"lookup", "compute", "write", "send"}))
ReActLoop(rt).run(task.goal_message())
print("1. allowlist of tool names      ->", evaluate(task, world).reason, world.outbox)

# Human approval via interrupt/resume: the run pauses, a decision arrives later, the run continues.
world, gate, rt = fresh(lambda t, w: ApprovalTools(t))  # no inline approver: raises Interrupt
loop = ReActLoop(rt)
result = loop.run(task.goal_message())
while result.status == "interrupted":
    call = result.pending
    approve = call.args["to"] == "ops"  # the reviewer's decision
    print(f"   paused for approval: {call.tool}({call.args}) -> {'approve' if approve else 'deny'}")
    if approve:
        gate.grant(call)
    result = loop.run(task.goal_message(), resume=result.history, pending=(call, approve))
print("2. approval (interrupt/resume)  ->", evaluate(task, world).reason, world.outbox)

# Capability token: minted by the root, attenuated before being handed to the agent.
secret = b"root-secret"
root = mint(secret, "session-42", {"tools": ["lookup", "compute", "write", "send"]})
agent_cap = attenuate(attenuate(root, {"arg": {"tool": "send", "name": "to", "pattern": "ops"}}), {"max_calls": 20})
world, cap_tools, rt = fresh(lambda t, w: CapabilityTools(t, secret, agent_cap, w.clock))
ReActLoop(rt).run(task.goal_message())
print("3. attenuated capability token  ->", evaluate(task, world).reason, world.outbox, f"(denied {cap_tools.denials} call)")

forged = type(agent_cap)(agent_cap.id, agent_cap.caveats[:1], agent_cap.sig)  # try to drop the caveats
print("   stripping caveats from the token keeps a valid signature:", verify_signature(secret, forged))
