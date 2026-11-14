# Examples

Thirteen standalone scripts. Each builds everything it needs, runs in well under a second, needs no network or API key, and ends by checking the final world state.

```bash
python examples/01_react_loop.py
```

| Script | Implementation area | What to look for |
|---|---|---|
| `01_react_loop.py` | Single-agent execution loop | The agent recovers from a relocated key by reading the error |
| `02_plan_execute.py` | Planner-executor workflow | One plan with `$ref` placeholders, one replan, three model calls in total |
| `03_verified_state_machine.py` | State-machine loop with verification | The transition list; the same model fails the task under ReAct |
| `04_supervisor_workers.py` | Supervisor-worker orchestration | The worker schedule, a crash and a reassignment |
| `05_peer_handoff.py` | Multi-agent communication | Each handoff envelope and how the transcript grows |
| `06_state_graph.py` | State machines | An interrupt, two resumes, per-node checkpoints (no model involved) |
| `07_durable_execution.py` | Durable execution and checkpointing | Two crashes after a non-idempotent send, recovery from an on-disk journal, zero duplicates |
| `08_tool_registries.py` | Tool registries | Prompt tokens for static, scoped and lazy registries; scopes cannot widen |
| `09_context_memory.py` | Context and memory management | A small window stalls; compaction and a ledger shrink the context |
| `10_failure_recovery.py` | Failure recovery | An outage under three strategies; a lost reply with and without idempotency keys |
| `11_trace_and_replay.py` | Execution logging and replay | Event log, span tree, exact replay, divergence detection |
| `12_model_routing.py` | Model routing | Success, cost and large-model share for four routers |
| `13_permissions_and_approval.py` | Permission and approval handling | An injected exfiltration under an allowlist, human approval and a capability token |

`tests/test_examples.py` runs every script in a fresh interpreter.
