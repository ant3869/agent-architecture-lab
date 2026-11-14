# Technical findings by topic

Each section states what published sources establish, then what this repository implements and measures. Quantitative claims attributed to papers are quoted from their abstracts and are *their* measurements on *their* benchmarks; numbers from this repository are labelled as such and come from [`experiments/RESULTS.md`](../experiments/RESULTS.md).

## 1. Execution loops and iterative task completion

- **Interleaving reasoning and acting** is the baseline. ReAct alternates a thought, an action and an observation, and reported absolute success-rate gains of 34% and 10% over imitation and reinforcement-learning baselines on ALFWorld and WebShop ([ReAct][yao2022react]).
- **Executable code as the action space** is an alternative to JSON tool calls; CodeAct reports up to 20% higher success rate across 17 models ([CodeAct][wang2024codeact]).
- **Search over reasoning paths** (Tree of Thoughts) raised Game-of-24 success from 4% to 74% with GPT-4 ([ToT][yao2023tot]) at the cost of many more model calls; it suits puzzles with cheap evaluation, not tool use with side effects.
- **Trial-level retry with verbal feedback** (Reflexion) reached 91% pass@1 on HumanEval ([Reflexion][shinn2023reflexion]). It presumes an environment that can be reset between trials.

In this repo: [`patterns/execution-loops`](../patterns/execution-loops/README.md). Three loops with different control structures are implemented and compared under identical injected errors.

## 2. Planning, execution, observation, verification

- **Plan first, then execute.** Plan-and-Solve showed that asking for a plan before solving improves zero-shot reasoning ([Plan-and-Solve][wang2023plansolve]).
- **Decouple the plan from observations.** ReWOO has the planner emit steps with variable placeholders that workers fill in, reporting 5x token efficiency and a 4% accuracy gain on HotpotQA ([ReWOO][xu2023rewoo]).
- **Compile the plan to a DAG and run independent calls in parallel.** LLMCompiler reports up to 3.7x latency speed-up and up to 6.7x cost savings versus ReAct ([LLMCompiler][kim2023llmcompiler]).
- **Verification is a separate role.** Anthropic's evaluator-optimizer workflow and the general advice to prefer predefined code paths where the task allows ([Building effective agents][anthropic-bea]).

Measured here: plan-and-execute used <!--n:loops|clean|plan_execute|total_tokens_mean|k-->995<!--/n--> tokens per clean 15-step task against <!--n:loops|clean|react|total_tokens_mean|k-->7.4k<!--/n--> for ReAct, the direction ReWOO reports. With 8% injected slips (half silent) both succeeded on <!--n:loops|noisy|react|success_rate|%-->56%<!--/n--> of tasks while a verify-before-effect graph succeeded on <!--n:loops|noisy|verified_graph|success_rate|%-->95%<!--/n-->.

## 3. Multi-agent orchestration and delegation

- **Conversation as the orchestration medium:** AutoGen ([AutoGen][wu2023autogen]), CAMEL role-play ([CAMEL][li2023camel]).
- **Encoding a process:** MetaGPT assigns roles and standard operating procedures and passes structured artefacts between them ([MetaGPT][hong2023metagpt]).
- **A lead agent with a ledger:** Magentic-One's orchestrator plans, tracks progress and re-plans around specialist agents ([Magentic-One][fourney2024magentic]).
- **Evidence for:** Anthropic reports a lead-plus-subagents system outperforming a single agent by 90.2% on an internal research evaluation, and attributes most of the gain to spending more tokens in parallel (token usage alone explained 80% of performance variance on BrowseComp) ([Anthropic][anthropic-multiagent]).
- **Evidence against:** the same post reports roughly 15x the tokens of a chat interaction. A taxonomy built from 1600+ annotated traces across 7 multi-agent frameworks identifies 14 failure modes and observes that gains over single agents on popular benchmarks are often minimal ([MAST][cemri2025mast]). Cognition's field report locates failures in what agents do *not* know about each other's work ([Cognition][cognition-multiagents]).

In this repo: [`patterns/orchestration`](../patterns/orchestration/README.md).

## 4. Supervisor-worker and peer-to-peer architectures

- **Supervisor-worker** corresponds to CrewAI's hierarchical process, which requires a manager model or agent ([CrewAI][crewai-processes]), and to the orchestrator-workers workflow ([Building effective agents][anthropic-bea]).
- **Peer-to-peer handoff** corresponds to Swarm and the Agents SDK, where a handoff is a tool call that transfers the conversation ([handoffs][openai-agents-handoffs], [Swarm][openai-swarm]).

Measured here (57-step decomposable tasks): supervisor <!--n:orchestration|no fault, 8 stages (57 steps)|supervisor, 1 worker/skill|total_tokens_mean|k-->11.1k<!--/n--> tokens with peak context <!--n:orchestration|no fault, 8 stages (57 steps)|supervisor, 1 worker/skill|peak_context_mean|0-->446<!--/n-->; single agent <!--n:orchestration|no fault, 8 stages (57 steps)|single agent (react)|total_tokens_mean|k-->82.9k<!--/n--> and <!--n:orchestration|no fault, 8 stages (57 steps)|single agent (react)|peak_context_mean|0-->2,269<!--/n-->; peer handoff <!--n:orchestration|no fault, 8 stages (57 steps)|peer handoff|total_tokens_mean|k-->165.8k<!--/n--> tokens. With an agent crash the supervisor completed <!--n:orchestration|ops agent dies right after its k-th tool call, k in 1..4 (4 stages, per-stage notifications)|supervisor (respawn)|success_rate|%-->50%<!--/n--> of tasks correctly (<!--n:orchestration|ops agent dies right after its k-th tool call, k in 1..4 (4 stages, per-stage notifications)|supervisor (respawn) + idem|success_rate|%-->100%<!--/n--> when calls carried idempotency keys) and an undurable handoff chain <!--n:orchestration|ops agent dies right after its k-th tool call, k in 1..4 (4 stages, per-stage notifications)|peer handoff|success_rate|%-->0%<!--/n-->.

## 5. Persistent state, checkpoints and recovery

- **Snapshot checkpointing:** LangGraph checkpointers save graph state per thread and enable resumption, human-in-the-loop and time travel ([LangGraph persistence][langgraph-persistence]).
- **Journal and replay:** Temporal re-executes workflow code against recorded history and therefore requires determinism ([Temporal][temporal-workflow-execution]); Restate and DBOS apply the same idea to ordinary functions ([Restate][restate-docs], [DBOS][dbos-docs]).
- **Compensation rather than rollback** for long-lived multi-step work goes back to sagas ([Sagas][sagas]).
- **Idempotency keys** make a retried request recognisable by the server ([Stripe][stripe-idempotency]).

In this repo: [`patterns/durable-execution`](../patterns/durable-execution/README.md). Every tool call boundary is crashed, before and after, for five strategies.

## 6. Memory management and context optimisation

- **Context is a finite resource that degrades.** Chroma's study of 18 models found performance "grows increasingly unreliable as input length grows" ([Context Rot][chroma-context-rot]); Anthropic uses the same term and recommends compaction, structured note-taking and sub-agents for long horizons ([Context engineering][anthropic-context]).
- **Tiered memory with explicit paging:** MemGPT treats the context window like RAM and external stores like disk ([MemGPT][packer2023memgpt]).
- **Retrieval by recency, importance and relevance, plus periodic reflection:** Generative Agents ([Generative Agents][park2023generative]).

Measured here at 57 steps: a 6-message window completed <!--n:memory|57 steps|window-6|success_rate|%-->0%<!--/n--> of tasks (livelock re-fetching evicted operands). Tokens per task: full history <!--n:memory|57 steps|full|total_tokens_mean|k-->82.9k<!--/n-->, window-16 <!--n:memory|57 steps|window-16|total_tokens_mean|k-->79.7k<!--/n-->, window-32 <!--n:memory|57 steps|window-32|total_tokens_mean|k-->101.7k<!--/n--> (a window can cost more than full history because of re-fetching), compaction <!--n:memory|57 steps|compaction-600|total_tokens_mean|k-->55.4k<!--/n-->, structured ledger <!--n:memory|57 steps|ledger|total_tokens_mean|k-->40.3k<!--/n-->. The simulator charges for context but does not model recall degradation, so the savings understate the benefit.

## 7. Tool integration and capability routing

- **Large tool sets hurt selection.** RAG-MCP reports that retrieving a relevant subset cut prompt tokens by over 50% and more than tripled tool-selection accuracy (43.13% vs 13.62%) ([RAG-MCP][gan2025ragmcp]); ToolLLM studies retrieval over 16,000+ APIs ([ToolLLM][qin2023toolllm]).
- **Deferred loading in production:** Anthropic's tool search tool is reported to reduce token usage by 85% while keeping the full library reachable; programmatic tool calling cut a research workload from 43,588 to 27,297 tokens ([Advanced tool use][anthropic-advanced-tools]).
- **Schemas and error channels:** MCP tools carry JSON Schema inputs, optional output schemas and structured content; validation failures belong in the tool result so the model can correct itself ([MCP tools][mcp-tools], [changes][mcp-changelog-2025-11-25]).

In this repo: [`patterns/tool-registry`](../patterns/tool-registry/README.md). With a 39-tool catalogue, prompt tokens per task were <!--n:tools|perfect model|static|prompt_tokens_mean|k-->33.4k<!--/n--> with everything exposed, <!--n:tools|perfect model|scoped|prompt_tokens_mean|k-->7.0k<!--/n--> scoped and <!--n:tools|perfect model|lazy|prompt_tokens_mean|k-->9.4k<!--/n--> with lazy discovery, the same order of saving as the published figures. Selection accuracy is not modelled.

## 8. Agent communication and interoperability

- **Agent-to-tool:** MCP ([spec][mcp-spec]). **Agent-to-agent:** A2A, with agent cards, task lifecycles and three transport bindings ([A2A][a2a-spec]).
- Both are evolving quickly; the MCP core dropped sessions and the handshake in 2026-07-28 ([changes][mcp-changelog-latest]).

In this repo: a TypeScript MCP server driven by unmodified Python loops, tested end to end; an in-process message bus whose envelope and card shapes follow A2A's vocabulary.

## 9. Concurrent execution and resource management

- Parallel tool calls (LLMCompiler) and parallel sub-agents (Anthropic's research system) trade tokens for wall-clock time ([LLMCompiler][kim2023llmcompiler], [Anthropic][anthropic-multiagent]).

Measured here with a virtual-time scheduler on 57-step tasks: makespan <!--n:orchestration|no fault, 8 stages (57 steps)|supervisor, 1 worker/skill|makespan_ms_mean|s-->39.6<!--/n-->s with one worker per skill and <!--n:orchestration|no fault, 8 stages (57 steps)|supervisor, 3 workers/skill|makespan_ms_mean|s-->23.0<!--/n-->s with three, at identical token cost. Real concurrency, rate limits and backpressure are not exercised (see limitations).

## 10. Model selection and cost optimisation

- **Cascades:** FrugalGPT reports matching the best single model with up to 98% cost reduction by trying cheaper models first and escalating ([FrugalGPT][chen2023frugalgpt]).
- **Learned routers:** RouteLLM reports cost reductions of over 2x in some cases without loss of quality ([RouteLLM][ong2024routellm]).

Measured here: on an unverified loop a cascade reached <!--n:routing|react|cascade (escalate on failure)|success_rate|%-->48%<!--/n--> against <!--n:routing|react|all-small|success_rate|%-->44%<!--/n--> for the small model alone (silent errors give no escalation signal). Paired with the verified graph it reached <!--n:routing|verified_graph|cascade (escalate on failure)|success_rate|%-->98%<!--/n--> at cost <!--n:routing|verified_graph|cascade (escalate on failure)|cost_mean|1-->17.1<!--/n-->, against <!--n:routing|verified_graph|all-large|success_rate|%-->100%<!--/n--> at <!--n:routing|verified_graph|all-large|cost_mean|1-->20.7<!--/n--> for the large model, and with a cheap verifier <!--n:routing|verified_graph|cascade, small verifier|success_rate|%-->94%<!--/n--> at <!--n:routing|verified_graph|cascade, small verifier|cost_mean|1-->7.4<!--/n-->. The published savings depend on a reliable quality signal; so do ours.

## 11. Sandboxing, authorization and security

- **Indirect prompt injection** turns retrieved content into instructions ([Greshake et al.][greshake2023injection]); OWASP lists prompt injection and excessive agency among the top LLM application risks ([OWASP][owasp-llm-top10]).
- **The lethal trifecta:** private data, untrusted content and an exfiltration channel together make data theft possible ([Willison][willison-trifecta]).
- **Defences by construction:** CaMeL separates control flow from untrusted data and enforces capability-based policies at tool-call time ([CaMeL][debenedetti2025camel]); macaroons give attenuable bearer tokens ([Macaroons][macaroons]).
- **Human approval has a cost:** the MCP specification asks for a human able to deny tool calls ([MCP tools][mcp-tools]); Anthropic reports that sandboxing cut permission prompts by 84% in internal use, i.e. boundaries can replace prompts ([Sandboxing][anthropic-sandboxing]).

In this repo: [`patterns/permissions`](../patterns/permissions/README.md). Process and filesystem sandboxing is out of scope; the pattern covers authorization at the tool boundary.

## 12. Error handling, retries and failure recovery

- **Backoff with jitter** avoids synchronised retry storms ([AWS][aws-backoff-jitter]). **Circuit breakers** stop calling a failing dependency after a threshold ([Fowler][fowler-circuit-breaker]). **Idempotency keys** make retries of side effects safe ([Stripe][stripe-idempotency]).
- For agents there is a third place to retry, the model, by showing it the error. MCP explicitly routes validation errors there ([changes][mcp-changelog-2025-11-25]).

In this repo: [`patterns/failure-recovery`](../patterns/failure-recovery/README.md). Under 30% transient faults model-mediated retry used <!--n:recovery|transient 30%|model-mediated|model_calls_mean|1-->20.3<!--/n--> model calls per task and runtime backoff <!--n:recovery|transient 30%|backoff|model_calls_mean|1-->16.5<!--/n-->. Through a 58s outage backoff alone took <!--n:recovery|outage 58s|backoff|sim_ms_mean|s-->71.8<!--/n-->s and a breaker with a replica fallback <!--n:recovery|outage 58s|breaker+fallback|sim_ms_mean|s-->26.2<!--/n-->s. With lost replies on a non-idempotent call, success was <!--n:recovery|ambiguous timeout 50%|backoff|success_rate|%-->54%<!--/n--> without idempotency keys and <!--n:recovery|ambiguous timeout 50%|backoff+idem|success_rate|%-->100%<!--/n--> with them.

## 13. Execution tracing and observability

- OpenTelemetry defines GenAI spans for agent creation, invocation, planning and tool execution with `gen_ai.*` attributes; the conventions are still marked *Development* ([OTel GenAI][otel-genai-agent-spans]).
- The Agents SDK traces runs by default ([tracing][openai-agents-tracing]); LangGraph's checkpoints double as a time-travel record ([persistence][langgraph-persistence]).

In this repo: [`patterns/tracing-replay`](../patterns/tracing-replay/README.md). One event stream feeds a JSONL log, an OTel-shaped span tree and a record/replay tape; replay reproduced the complete event stream in <!--n:tracing|*|react|replay_identical|%-->100%<!--/n--> of recorded runs.

## 14. Agent evaluation and performance measurement

- **End-state grading on realistic tasks:** SWE-bench (resolving real GitHub issues) ([SWE-bench][jimenez2023swebench]), GAIA ([GAIA][mialon2023gaia]), AgentBench across eight environments ([AgentBench][liu2023agentbench]).
- **Consistency matters as much as peak success:** tau-bench found state-of-the-art function-calling agents succeeding on under 50% of tasks and under 25% when the same task must succeed eight times in a row ([tau-bench][yao2024taubench]).
- **Failure taxonomies** for multi-agent systems ([MAST][cemri2025mast]).

In this repo: [`docs/methodology.md`](../docs/methodology.md). Success is judged on the final world state, failures are typed (wrong effect, duplicate effect, incomplete, exfiltration), noise is paired across architectures, and every table is reproducible to the byte. What the harness cannot tell you, and the benchmarks above can, is how a real model behaves.

<!-- refs:start -->
[a2a-spec]: https://a2a-protocol.org/latest/specification/ "Agent2Agent (A2A) Protocol specification"
[anthropic-advanced-tools]: https://www.anthropic.com/engineering/advanced-tool-use "Introducing advanced tool use on the Claude Developer Platform"
[anthropic-bea]: https://www.anthropic.com/engineering/building-effective-agents "Building effective agents"
[anthropic-context]: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents "Effective context engineering for AI agents"
[anthropic-multiagent]: https://www.anthropic.com/engineering/multi-agent-research-system "How we built our multi-agent research system"
[anthropic-sandboxing]: https://www.anthropic.com/engineering/claude-code-sandboxing "Beyond permission prompts: making Claude Code more secure and autonomous"
[aws-backoff-jitter]: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/ "Exponential Backoff And Jitter"
[cemri2025mast]: https://arxiv.org/abs/2503.13657 "Why Do Multi-Agent LLM Systems Fail?"
[chen2023frugalgpt]: https://arxiv.org/abs/2305.05176 "FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance"
[chroma-context-rot]: https://research.trychroma.com/context-rot "Context Rot: How Increasing Input Tokens Impacts LLM Performance"
[cognition-multiagents]: https://cognition.ai/blog/dont-build-multi-agents "Don't Build Multi-Agents"
[crewai-processes]: https://docs.crewai.com/en/concepts/processes "CrewAI: Processes"
[dbos-docs]: https://docs.dbos.dev/ "DBOS documentation"
[debenedetti2025camel]: https://arxiv.org/abs/2503.18813 "Defeating Prompt Injections by Design"
[fourney2024magentic]: https://arxiv.org/abs/2411.04468 "Magentic-One: A Generalist Multi-Agent System for Solving Complex Tasks"
[fowler-circuit-breaker]: https://martinfowler.com/bliki/CircuitBreaker.html "CircuitBreaker"
[gan2025ragmcp]: https://arxiv.org/abs/2505.03275 "RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection via Retrieval-Augmented Generation"
[greshake2023injection]: https://arxiv.org/abs/2302.12173 "Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection"
[hong2023metagpt]: https://arxiv.org/abs/2308.00352 "MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework"
[jimenez2023swebench]: https://arxiv.org/abs/2310.06770 "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?"
[kim2023llmcompiler]: https://arxiv.org/abs/2312.04511 "An LLM Compiler for Parallel Function Calling"
[langgraph-persistence]: https://docs.langchain.com/oss/python/langgraph/persistence "LangGraph persistence (checkpointers and stores)"
[li2023camel]: https://arxiv.org/abs/2303.17760 "CAMEL: Communicative Agents for 'Mind' Exploration of Large Language Model Society"
[liu2023agentbench]: https://arxiv.org/abs/2308.03688 "AgentBench: Evaluating LLMs as Agents"
[macaroons]: https://research.google/pubs/macaroons-cookies-with-contextual-caveats-for-decentralized-authorization-in-the-cloud/ "Macaroons: Cookies with Contextual Caveats for Decentralized Authorization in the Cloud"
[mcp-changelog-2025-11-25]: https://modelcontextprotocol.io/specification/2025-11-25/changelog "MCP specification 2025-11-25: key changes"
[mcp-changelog-latest]: https://modelcontextprotocol.io/specification/latest/changelog "MCP specification 2026-07-28: key changes"
[mcp-spec]: https://modelcontextprotocol.io/specification/latest "Model Context Protocol specification"
[mcp-tools]: https://modelcontextprotocol.io/specification/latest/server/tools "MCP specification: Tools"
[mialon2023gaia]: https://arxiv.org/abs/2311.12983 "GAIA: a benchmark for General AI Assistants"
[ong2024routellm]: https://arxiv.org/abs/2406.18665 "RouteLLM: Learning to Route LLMs with Preference Data"
[openai-agents-handoffs]: https://openai.github.io/openai-agents-python/handoffs/ "OpenAI Agents SDK: Handoffs"
[openai-agents-tracing]: https://openai.github.io/openai-agents-python/tracing/ "OpenAI Agents SDK: Tracing"
[openai-swarm]: https://github.com/openai/swarm "Swarm (experimental, educational)"
[otel-genai-agent-spans]: https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md "OpenTelemetry semantic conventions for GenAI agent and framework spans"
[owasp-llm-top10]: https://genai.owasp.org/llm-top-10/ "OWASP Top 10 for LLM Applications 2025"
[packer2023memgpt]: https://arxiv.org/abs/2310.08560 "MemGPT: Towards LLMs as Operating Systems"
[park2023generative]: https://arxiv.org/abs/2304.03442 "Generative Agents: Interactive Simulacra of Human Behavior"
[qin2023toolllm]: https://arxiv.org/abs/2307.16789 "ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs"
[restate-docs]: https://docs.restate.dev/ "Restate documentation"
[sagas]: https://dl.acm.org/doi/10.1145/38713.38742 "Sagas"
[shinn2023reflexion]: https://arxiv.org/abs/2303.11366 "Reflexion: Language Agents with Verbal Reinforcement Learning"
[stripe-idempotency]: https://stripe.com/blog/idempotency "Designing robust and predictable APIs with idempotency"
[temporal-workflow-execution]: https://docs.temporal.io/workflow-execution "Temporal: Workflow Execution"
[wang2023plansolve]: https://arxiv.org/abs/2305.04091 "Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models"
[wang2024codeact]: https://arxiv.org/abs/2402.01030 "Executable Code Actions Elicit Better LLM Agents"
[willison-trifecta]: https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ "The lethal trifecta for AI agents: private data, untrusted content, and external communication"
[wu2023autogen]: https://arxiv.org/abs/2308.08155 "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation"
[xu2023rewoo]: https://arxiv.org/abs/2305.18323 "ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models"
[yao2022react]: https://arxiv.org/abs/2210.03629 "ReAct: Synergizing Reasoning and Acting in Language Models"
[yao2023tot]: https://arxiv.org/abs/2305.10601 "Tree of Thoughts: Deliberate Problem Solving with Large Language Models"
[yao2024taubench]: https://arxiv.org/abs/2406.12045 "tau-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains"
<!-- refs:end -->
