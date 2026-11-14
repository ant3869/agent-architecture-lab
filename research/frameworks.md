# Frameworks and protocols: what they actually do

Scope: the systems named in the project brief plus the durable-execution engines the agent frameworks borrow from. Every statement below is tied to a primary source in [`sources.toml`](sources.toml); statements about release status were read from the vendors' own pages on 2026-11-14. Where this document says nothing about a feature, that is not a claim that the feature is absent.

## One-paragraph profiles

**LangGraph.** Positions itself as an orchestration runtime whose focus is "durable execution, streaming, human-in-the-loop, and persistence" ([overview][langgraph-overview]). Applications are explicit state graphs. Persistence has two layers: *checkpointers* save a thread's graph state as checkpoints addressed by `thread_id`, and *stores* hold application data across threads ([persistence][langgraph-persistence]). Human-in-the-loop is an `interrupt()` call inside a node, resumed with `Command(resume=...)`; on resume "the node restarts from the beginning of the node where the interrupt was called", so code before the interrupt runs again ([interrupts][langgraph-interrupts]). That last sentence is the single most consequential design fact for anyone putting side effects in nodes.

**OpenAI Agents SDK.** A deliberately small set of primitives: agents, handoffs, guardrails, sessions and tracing ([docs][openai-agents-docs]). Control moves between agents by *handoff*, and "handoffs are represented as tools to the LLM" (a handoff to `Refund Agent` becomes a tool named `transfer_to_refund_agent`); the receiving agent sees the conversation history unless an `input_filter` changes it ([handoffs][openai-agents-handoffs]). Guardrails validate input, output and tool calls and can trip a wire that halts the run ([guardrails][openai-agents-guardrails]). Tracing is enabled by default ([tracing][openai-agents-tracing]). It is the production successor of Swarm, which OpenAI describes as experimental and educational ([Swarm README][openai-swarm]).

**CrewAI.** Two layers. *Crews* are role-based agent teams run under a *process*: sequential (tasks in order) or hierarchical (a manager, supplied as `manager_llm` or `manager_agent`, delegates and reviews) ([processes][crewai-processes]). *Flows* are "structured, event-driven workflows" with managed state, wired with decorators such as `@start` and `@listen` ([flows][crewai-flows]). The practical split: Crews put control in the model, Flows put it in code.

**AutoGen and Microsoft Agent Framework.** AutoGen introduced multi-agent *conversation* as a programming model ([paper][wu2023autogen]); its later Core API is event-driven message passing with local and distributed runtimes ([README][autogen-repo]). The same README now states that AutoGen is archived and in maintenance mode and that new work should use Microsoft Agent Framework, which Microsoft describes as "the direct successor" to both Semantic Kernel and AutoGen, adding graph-based workflows for explicit multi-agent orchestration ([overview][ms-agent-framework]). Treat AutoGen as historically important and its patterns as portable, not as a dependency to adopt today.

**Model Context Protocol (MCP).** A client-server protocol through which an application gives a model access to tools, resources and prompts ([spec][mcp-spec]). Three facts matter for architecture. First, the tools specification says there "SHOULD always be a human in the loop with the ability to deny tool invocations" and that tool annotations must be treated as untrusted unless the server is trusted ([tools][mcp-tools]). Second, input-validation failures should be returned as tool execution errors, not protocol errors, "to enable model self-correction" ([2025-11-25 changes][mcp-changelog-2025-11-25]). Third, the protocol is moving toward statelessness: the 2026-07-28 revision removes protocol-level sessions and the `initialize` handshake, adds `server/discover`, and moves the experimental *tasks* feature (introduced in 2025-11-25) out of the core into an extension ([2026-07-28 changes][mcp-changelog-latest]). The security guidance catalogues confused-deputy, token-passthrough and SSRF attacks ([security][mcp-security]).

**Agent2Agent (A2A).** A protocol for agents to discover and delegate to other agents as opaque peers, governed under the Linux Foundation; the latest released specification is 1.0.0 ([spec][a2a-spec]). An agent publishes an *Agent Card* at `/.well-known/agent-card.json`. Work is a *Task* with a lifecycle (submitted, working, input-required, auth-required, completed, failed, canceled, rejected). The protocol is defined abstractly with three bindings: JSON-RPC, gRPC and HTTP+JSON.

**Durable-execution engines (Temporal, Restate, DBOS).** Not agent frameworks, but the source of the journal-and-replay pattern. Temporal resumes a workflow by *replay*: the code is re-executed and the commands it generates are checked against the recorded event history, which is why workflow code must be deterministic ([Temporal][temporal-workflow-execution]). Restate describes the same idea as code that "stores completed steps and resumes from where it left off" ([Restate][restate-docs]); DBOS checkpoints workflow steps in a database ([DBOS][dbos-docs]).

## Comparison

| | LangGraph | OpenAI Agents SDK | CrewAI | AutoGen / MS Agent Framework |
|---|---|---|---|---|
| Who decides the next step | Code: graph edges and routers; a node may call a model | The model, by calling tools or a handoff tool | Crew: the process (and, if hierarchical, a manager model). Flow: code | Conversation/group-chat manager (AutoGen); graph workflows (Agent Framework) |
| Unit of composition | Node in a state graph | Agent with tools and handoffs | Agent with a role, in a crew; step in a flow | Agent exchanging messages |
| State model | Explicit shared state object, checkpointed | Conversation history held by a session | Task outputs passed along; flow state object | Message history per agent |
| Persistence | Checkpointer per thread + cross-thread store | Sessions persist history | Flow state | Runtime-dependent |
| Human-in-the-loop | `interrupt()` + resume; node re-executes | Guardrails and tool approval | Human input on tasks | Human proxy agent pattern |
| Multi-agent primitive | Subgraphs, supervisor or swarm graphs built from nodes | Handoff (transfer of the conversation) | Delegation by process | Group chat, message passing |
| Closest pattern in this repo | `verified_graph`, `statemachine`, snapshot durability | `handoff` orchestration, approval middleware | `supervisor` (hierarchical), `plan_execute` (flows) | `supervisor`, message bus |

| | MCP | A2A |
|---|---|---|
| Connects | A model-hosting application to tools and data | An agent to another agent |
| The remote side is | A tool server: its internals are schemas you can read | An opaque agent: you see its card and its task states, not its tools |
| Unit of work | A tool call (request/response; long-running work via the tasks extension) | A task with a lifecycle and artifacts |
| Discovery | Tool listing from a connected server | Agent Card at a well-known URL |
| In this repo | [`integrations/mcp-tool-server`](../integrations/mcp-tool-server) + `agentlab.integrations.mcp_tools` (tested across languages) | Envelope and card shapes in `orchestration/bus.py` are modelled on it; no wire implementation (see roadmap) |

## Differences that change an engineering decision

1. **Model-directed versus code-directed control is the real axis, not the brand.** Anthropic's taxonomy separates *workflows* ("LLMs and tools are orchestrated through predefined code paths") from *agents* ("LLMs dynamically direct their own processes") ([Building effective agents][anthropic-bea]). LangGraph graphs and CrewAI Flows sit on the workflow side; handoff chains and hierarchical crews sit on the agent side. The loops experiment in this repo measures what that choice costs: with identical model errors, the code-directed verified graph completes far more tasks than the model-directed loops because code can enforce "verify before side effects" and a prompt cannot (see [`experiments/RESULTS.md`](../experiments/RESULTS.md), *Execution loops*).

2. **Handoff transfers the transcript; delegation transfers a brief.** The Agents SDK forwards conversation history to the receiving agent by default ([handoffs][openai-agents-handoffs]). A supervisor that writes a sub-brief and reads back a condensed result isolates context instead. Cognition argues for the former on reliability grounds ("share context"; "actions carry implicit decisions") ([Don't Build Multi-Agents][cognition-multiagents]); Anthropic's research system uses the latter for parallelism and reports about 15x the token use of chat ([multi-agent research system][anthropic-multiagent]). The orchestration experiment reproduces the mechanism in both directions: handoff costs the most tokens on long tasks because the transcript travels, while isolated workers cost the least on *cleanly decomposable* tasks.

3. **Checkpoint-and-re-execute versus journal-and-replay.** LangGraph resumes by re-running the interrupted node from its start ([interrupts][langgraph-interrupts]); Temporal-style engines replay recorded results so completed steps are never re-executed ([Temporal][temporal-workflow-execution]). Both are at-least-once for whatever was in flight at the crash. The durability experiment shows the consequence exhaustively: with either strategy the only failures are crashes immediately after a non-idempotent effect, and idempotency keys remove them.

4. **Tool-level trust differs by protocol.** MCP tells clients to keep a human able to deny calls and to distrust server-supplied annotations ([tools][mcp-tools]). A2A treats the peer as opaque, so authorization has to be expressed in what you send it, not in what you can inspect. Neither protocol constrains *arguments* for you; that is application policy (see the permissions pattern).

5. **Protocol churn is a design input.** Between the 2025-11-25 and 2026-07-28 MCP revisions the handshake and session model changed ([changes][mcp-changelog-latest]). This repo's MCP bridge therefore uses the official SDKs on both sides and tests them against each other, rather than re-implementing the wire format.

<!-- refs:start -->
[a2a-spec]: https://a2a-protocol.org/latest/specification/ "Agent2Agent (A2A) Protocol specification"
[anthropic-bea]: https://www.anthropic.com/engineering/building-effective-agents "Building effective agents"
[anthropic-multiagent]: https://www.anthropic.com/engineering/multi-agent-research-system "How we built our multi-agent research system"
[autogen-repo]: https://github.com/microsoft/autogen "microsoft/autogen README"
[cognition-multiagents]: https://cognition.ai/blog/dont-build-multi-agents "Don't Build Multi-Agents"
[crewai-flows]: https://docs.crewai.com/en/concepts/flows "CrewAI: Flows"
[crewai-processes]: https://docs.crewai.com/en/concepts/processes "CrewAI: Processes"
[dbos-docs]: https://docs.dbos.dev/ "DBOS documentation"
[langgraph-interrupts]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph interrupts"
[langgraph-overview]: https://docs.langchain.com/oss/python/langgraph/overview "LangGraph overview"
[langgraph-persistence]: https://docs.langchain.com/oss/python/langgraph/persistence "LangGraph persistence (checkpointers and stores)"
[mcp-changelog-2025-11-25]: https://modelcontextprotocol.io/specification/2025-11-25/changelog "MCP specification 2025-11-25: key changes"
[mcp-changelog-latest]: https://modelcontextprotocol.io/specification/latest/changelog "MCP specification 2026-07-28: key changes"
[mcp-security]: https://modelcontextprotocol.io/specification/latest/basic/security_best_practices "MCP specification: Security best practices"
[mcp-spec]: https://modelcontextprotocol.io/specification/latest "Model Context Protocol specification"
[mcp-tools]: https://modelcontextprotocol.io/specification/latest/server/tools "MCP specification: Tools"
[ms-agent-framework]: https://learn.microsoft.com/en-us/agent-framework/overview/ "Microsoft Agent Framework overview"
[openai-agents-docs]: https://openai.github.io/openai-agents-python/ "OpenAI Agents SDK documentation"
[openai-agents-guardrails]: https://openai.github.io/openai-agents-python/guardrails/ "OpenAI Agents SDK: Guardrails"
[openai-agents-handoffs]: https://openai.github.io/openai-agents-python/handoffs/ "OpenAI Agents SDK: Handoffs"
[openai-agents-tracing]: https://openai.github.io/openai-agents-python/tracing/ "OpenAI Agents SDK: Tracing"
[openai-swarm]: https://github.com/openai/swarm "Swarm (experimental, educational)"
[restate-docs]: https://docs.restate.dev/ "Restate documentation"
[temporal-workflow-execution]: https://docs.temporal.io/workflow-execution "Temporal: Workflow Execution"
[wu2023autogen]: https://arxiv.org/abs/2308.08155 "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation"
<!-- refs:end -->
