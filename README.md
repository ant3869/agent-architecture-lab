# Agent Architecture Lab

**Which agent architecture is appropriate for a particular engineering problem, what alternatives exist, and where can I find tested implementations?**

This repository answers that question with a catalogue of nine engineering problems. Each entry gives at least three distinct solutions, a diagram, a working implementation with tests, and a comparison measured by running the alternatives through the same scenarios, failure injections included. It is a reference library and a test bench, not another agent framework.

| If you want to… | Go to |
|---|---|
| Pick a pattern for a problem you have | [`docs/decision-guide.md`](docs/decision-guide.md) |
| Browse problems and their alternatives | [`patterns/`](patterns/README.md) |
| Read the code | [`src/agentlab/`](src/agentlab) and [`examples/`](examples/README.md) |
| See what was measured, and how | [`experiments/RESULTS.md`](experiments/RESULTS.md), [`docs/methodology.md`](docs/methodology.md) |
| Check the research and sources | [`research/`](research/README.md) |
| Use a pattern in your own system | [`docs/integration.md`](docs/integration.md) |
| Explore interactively | [`explorer/`](explorer/README.md) |
| Add to the catalogue | [`docs/extending.md`](docs/extending.md), [`AGENTS.md`](AGENTS.md) |

## The catalogue

| Problem | Implemented solutions | Headline measurement (this repository's simulator) |
|---|---|---|
| [Execution loops](patterns/execution-loops/README.md) | ReAct, Plan-and-Execute, Verified state-machine loop | With 8% injected model slips, half of them silent: ReAct <!--n:loops|noisy|react|success_rate|%-->56%<!--/n-->, Plan-and-Execute <!--n:loops|noisy|plan_execute|success_rate|%-->56%<!--/n-->, verified graph <!--n:loops|noisy|verified_graph|success_rate|%-->95%<!--/n--> task success |
| [Orchestration](patterns/orchestration/README.md) | Single agent, Supervisor-worker, Peer handoff | 57-step task: single agent <!--n:orchestration|no fault, 8 stages (57 steps)|single agent (react)|total_tokens_mean|k-->82.9k<!--/n--> tokens, supervisor <!--n:orchestration|no fault, 8 stages (57 steps)|supervisor, 1 worker/skill|total_tokens_mean|k-->11.1k<!--/n-->, handoff <!--n:orchestration|no fault, 8 stages (57 steps)|peer handoff|total_tokens_mean|k-->165.8k<!--/n--> |
| [Durable execution](patterns/durable-execution/README.md) | Restart, Snapshot checkpoints, Journal replay, Idempotency keys | Crash at every tool-call boundary: journal <!--n:durability|single crash (exhaustive)|journal|success_rate|%-->88%<!--/n--> correct without idempotency keys, <!--n:durability|single crash (exhaustive)|journal+idem|success_rate|%-->100%<!--/n--> with |
| [Tool registries](patterns/tool-registry/README.md) | Static, Capability-scoped, Lazy discovery | 39-tool catalogue: <!--n:tools|perfect model|static|prompt_tokens_mean|k-->33.4k<!--/n--> prompt tokens static, <!--n:tools|perfect model|scoped|prompt_tokens_mean|k-->7.0k<!--/n--> scoped, <!--n:tools|perfect model|lazy|prompt_tokens_mean|k-->9.4k<!--/n--> lazy |
| [Context and memory](patterns/context-memory/README.md) | Full history, Sliding window, Compaction, Fact ledger | 57 steps: full <!--n:memory|57 steps|full|total_tokens_mean|k-->82.9k<!--/n--> tokens, compaction <!--n:memory|57 steps|compaction-600|total_tokens_mean|k-->55.4k<!--/n-->, ledger <!--n:memory|57 steps|ledger|total_tokens_mean|k-->40.3k<!--/n-->; a 6-message window finished <!--n:memory|57 steps|window-6|success_rate|%-->0%<!--/n--> |
| [Failure recovery](patterns/failure-recovery/README.md) | Model-mediated retry, Backoff, Circuit breaker + fallback, Idempotency keys | 58s outage: <!--n:recovery|outage 58s|backoff|sim_ms_mean|s-->71.8<!--/n-->s with backoff, <!--n:recovery|outage 58s|breaker+fallback|sim_ms_mean|s-->26.2<!--/n-->s with breaker and replica |
| [Model routing](patterns/model-routing/README.md) | Static, Role-based, Cascade | Verified graph: all-large <!--n:routing|verified_graph|all-large|success_rate|%-->100%<!--/n--> at cost <!--n:routing|verified_graph|all-large|cost_mean|1-->20.7<!--/n-->; cascade with a small verifier <!--n:routing|verified_graph|cascade, small verifier|success_rate|%-->94%<!--/n--> at <!--n:routing|verified_graph|cascade, small verifier|cost_mean|1-->7.4<!--/n--> |
| [Permissions](patterns/permissions/README.md) | Allowlist, Human approval (interrupt/resume), Capability tokens | Injected exfiltration executed: allowlist <!--n:permissions|model always obeys injected text|allowlist (tool names)|exfil_mean|%-->100%<!--/n-->, capability token <!--n:permissions|model always obeys injected text|capability token (argument-scoped)|exfil_mean|%-->0%<!--/n--> |
| [Tracing and replay](patterns/tracing-replay/README.md) | Event log, Span tree, Record/replay | Replay reproduced the full event stream in <!--n:tracing|*|react|replay_identical|%-->100%<!--/n--> of recorded runs |

These numbers compare architectures under an explicit, parameterised error model. They are **not** measurements of any real language model; read [`docs/limitations.md`](docs/limitations.md) before quoting them.

## Quick start

Requirements: Python 3.11 or newer. No API keys and no network are needed for the library, the examples, the experiments or the core tests.

1. Create an environment and install the library.

```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
```

2. Run one example.

```bash
python examples/03_verified_state_machine.py
```

3. Run the tests.

```bash
pytest
```

4. Reproduce every published number (about one minute; the digest printed must match `experiments/results/manifest.json`).

```bash
python -m experiments.run_all
```

5. Open the explorer.

```bash
cd explorer && npm install && npm run dev
```

Optional extras: `pip install -e ".[mcp]"` plus `cd integrations/mcp-tool-server && npm install && npm run build` enables the cross-language MCP tests; `pip install -e ".[anthropic]"` enables the real-model adapter.

## Repository layout

```
research/        Findings by topic, framework comparison, bibliography with verification status
patterns/        One folder per problem: pattern.toml (source of truth) and a generated README
src/agentlab/    The implementations (standard library only)
  core/            types, runtime (single metering/tracing choke point), tracer, replay
  sim/             deterministic world, task generator, simulated model
  loops/           react, plan_execute, verified_graph
  statemachine/    state-graph engine with checkpoints and interrupts
  orchestration/   message bus, supervisor-worker, peer handoff
  durability/      snapshot store, journal, crash injection
  memory/ tools/ recovery/ routing/ permissions/    composable policies and middleware
  integrations/    MCP tool bridge, Anthropic model adapter
  eval/            the common evaluation harness
examples/        13 standalone runnable scripts, one per implementation area
experiments/     10 reproducible experiments, results/*.json and RESULTS.md
tests/           unit, property, example, reproducibility and interop tests
integrations/    TypeScript MCP tool server driven by the Python loops
explorer/        React + TypeScript + Tailwind + Vite reference explorer (static)
docs/            decision guide, methodology, integration, limitations, roadmap, extending
scripts/         build_catalog.py (generates docs and explorer data), verify_sources.py
```

## How the pieces fit

Every architecture is written against two small protocols, `Model` and `ToolExecutor` ([`core/types.py`](src/agentlab/core/types.py)), and reaches them only through `Runtime` ([`core/runtime.py`](src/agentlab/core/runtime.py)), which meters and traces every call identically. Policies are wrappers around those protocols, so they compose:

```python
tools = IdempotentTools(CircuitBreakerTools(RetryingTools(registry, clock), clock, fallbacks={...}), run_id)
tools = CapabilityTools(tools, secret, token, clock)                 # authorization
session = DurableSession(SQLiteJournal("run.sqlite"), run_id)        # durability
rt = Runtime(session.model(model), session.tools(tools), tracer=Tracer(clock))
result = ReActLoop(rt, memory=FactLedger()).run(goal)
```

Swap `model` for `agentlab.integrations.anthropic_model.AnthropicModel()` to run the same stack on a real model, or `registry` for `MCPToolset(...)` to drive tools on any MCP server.

## Status

Implemented and tested: everything marked *implemented* in [`patterns/README.md`](patterns/README.md). Documented but not implemented: Reflexion, blackboard orchestration, learned routing, OS-level sandboxing, an A2A wire binding. See [`docs/roadmap.md`](docs/roadmap.md) for priorities and [`docs/limitations.md`](docs/limitations.md) for what the results do and do not show.

MIT licensed.
