# Expansion roadmap

Ordered by how much each item would increase the trustworthiness or usefulness of the catalogue. Each item names what "done" means so it can be picked up independently.

## P0: close the gap to real models

1. **Calibrate the error model against a real model.** Run the loops experiment's task family through `AnthropicModel` on a small fixed set, classify failures as loud or silent, and report the observed slip rate and silent fraction next to the simulated assumptions. *Done when* `experiments/RESULTS.md` has a clearly separated, opt-in section with live-model numbers and their cost.
2. **Structured-output prompts for `plan`, `verify`, `decompose`, `summarize`.** *Done when* Plan-and-Execute, the verified graph and the supervisor run end to end on a real model, with contract tests for the parsers.
3. **Exercise the Anthropic adapter live** behind an environment flag in CI. *Done when* a recorded tape of a live run is committed and replayed by the default test suite.

## P1: fill the largest pattern gaps

4. **A2A wire binding** for the message bus (agent card at the well-known path, JSON-RPC task send and get) with a cross-language interop test in the style of the MCP one.
5. **Blackboard / group-chat orchestration** as a third implemented topology, added to the orchestration experiment.
6. **Reflexion loop** with a resettable world, and an experiment that shows where it stops being usable (non-resettable effects).
7. **Compensation (sagas)** for multi-step effects that cannot be made idempotent, with a failure experiment on partial completion.
8. **A lossy summariser and a context-rot model** so the memory experiment can penalise long contexts and imperfect summaries instead of only charging for them.
9. **Real concurrency**: an asyncio runtime with bounded parallelism, rate limiting and backpressure, measured against the virtual-time schedule.
10. **Decomposition errors** in the simulator (missing, overlapping or mis-specified subtasks) so the multi-agent experiment includes the failure class the literature emphasises.

## P2: breadth and polish

11. **Data-flow tracking** (taint from untrusted tool output to side-effect arguments) as a fourth permissions solution.
12. **Sandboxing pattern** with a container-based example and a threat-model page.
13. **Learned router** trained on recorded outcomes from the cascade.
14. **OpenTelemetry exporter** that sends the span tree to a collector, with a compatibility test against the current GenAI conventions.
15. **Prompt-caching-aware cost model**, which will change the relative cost of full history versus compaction.
16. **Property-based tests** for the journal (arbitrary crash sequences) and the capability tokens.
17. **Publish the explorer** to a static host from CI, and split the diagram bundle further.
18. **More task families**: branching tasks, tasks with unstructured tool output, long-running tasks with waiting.

## How priorities were set

P0 items attack the main threat to validity (simulated model). P1 items are patterns that readers will look for and not find, or places where the simulator currently favours one side. P2 items widen coverage without changing any existing conclusion.
