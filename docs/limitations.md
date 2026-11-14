# Known limitations

Read this before relying on a number or a pattern from this repository.

## What the measurements are not

- **They are not benchmarks of a language model.** The "model" is a deterministic simulator with a parameterised error process ([`methodology.md`](methodology.md)). Results show how *architectures* respond to a given kind and rate of error. They do not show how often a real model makes those errors.
- **The error model is simple.** Slips are independent per attempt; real models make correlated and systematic errors. The simulator never mis-plans structurally (it never omits or mis-orders a step), which flatters plan-first designs. Decomposition by the supervisor is always correct, which flatters multi-agent designs.
- **The verifier is independent of the actor.** A verifier that shares the actor's blind spots catches less than the modelled miss rate suggests.
- **Context has a price but no penalty.** Tokens are charged, but the simulator's accuracy does not degrade with context length. Published evidence says real models do degrade, so the benefit of context management is understated here.
- **Tokens are an estimate** (characters / 4 over the real message text), not a tokenizer count. Prompt caching, which changes the economics of re-reading a stable prefix, is not modelled. Costs are in abstract units with an assumed 12x price ratio between the two simulated models.
- **Tasks are synthetic** and of one family: read, compute, write, notify, with clean dependency structure and compact structured tool outputs. Open-ended research, coding and conversational tasks behave differently; in particular the supervisor's token savings should not be expected there.
- **Time is simulated.** Latencies and timeouts are constants. Parallel speed-ups come from a virtual-time schedule, not from concurrent execution; rate limits, backpressure and contention are not exercised.
- **Security results validate mechanisms, not attack resistance.** The injection is a fixed marker and susceptibility is a parameter. Showing that a capability check blocks a disallowed recipient says nothing about how hard it is to craft an attack that stays inside the allowed set.
- **Statistics.** Rates are over 50 to 520 simulated runs per cell with Wilson intervals; because noise is paired, differences between architectures are more reliable than the absolute rates.

## What was not run

- **No third-party agent framework was executed.** Statements about LangGraph, the OpenAI Agents SDK, CrewAI, AutoGen, Microsoft Agent Framework, Temporal, Restate and DBOS come from their documentation as fetched on the date in [`research/verification.json`](../research/verification.json). The implementations here are independent reference implementations of the patterns those systems embody, not ports, and no performance claim is made about any framework.
- **The Anthropic adapter has not been called against the live API.** It is covered by contract tests against a stub client only. Request parameters were checked against the installed SDK's signatures.
- **MCP interoperability is tested over the stdio transport only**, between the official Python and TypeScript SDK versions installed at build time. The HTTP transport and authorization flows are not exercised.
- **One source could not be fetched automatically** (the ACM page for *Sagas*); it is marked `unverified` in the bibliography.

## What is not implemented

- The A2A protocol. The message bus borrows its vocabulary (agent cards, task states) and nothing else.
- Reflexion-style trial retry, blackboard / group-chat orchestration, learned routing, data-flow (taint) tracking, compensating transactions (sagas).
- Operating-system sandboxing of code execution, files or network. The permissions pattern covers authorization at the tool boundary only.
- Asynchronous or streaming execution. All loops are synchronous.
- Structured-output prompts for running the plan, verify, decompose and summarize roles on a real model.
- Distributed deployment: the bus, breaker state and stores are in-process (SQLite for persistence).

## Engineering caveats

- Journal replay requires the agent code to be deterministic given recorded results. This holds for the code here by construction; your own code needs the same discipline, and a code change between crash and recovery can be refused with `NonDeterminismError`.
- Snapshot checkpoints write the full state each time; the growth is quadratic in run length and is visible in the durability results.
- The capability token is a bearer credential signed with a shared secret. Key distribution, rotation and revocation are out of scope.
- The idempotency layer assumes the backend honours keys indefinitely.
- The explorer's diagram library is large; it is loaded only when a diagram is shown, but the first diagram costs a noticeable download.
