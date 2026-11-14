# Engineering decisions

The decisions that shaped this repository, each with the evidence that supports it. Numbers are bound to [`experiments/RESULTS.md`](../experiments/RESULTS.md).

**1. Compare architectures on a deterministic simulator, not on a live model.**
A live model adds run-to-run variance and cost, and makes results unrepeatable. Every experiment here reproduces to an identical SHA-256 digest, verified by the test suite. The cost is external validity; see [`limitations.md`](limitations.md) and roadmap item 1.

**2. Make the simulated model stateless, with knowledge limited to its visible context.**
This is what lets context and durability experiments mean something. Evidence that it bites: nobody scripted the sliding-window failure, yet a 6-message window completed <!--n:memory|57 steps|window-6|success_rate|%-->0%<!--/n--> of 57-step tasks, and a 32-message window used <!--n:memory|57 steps|window-32|total_tokens_mean|k-->101.7k<!--/n--> tokens against <!--n:memory|57 steps|full|total_tokens_mean|k-->82.9k<!--/n--> for full history because evicted values had to be fetched again.

**3. Pair the noise across architectures.**
Error draws are keyed by (seed, task, step, attempt), so differences are structural. Evidence: ReAct and Plan-and-Execute succeed on exactly the same tasks under noise (<!--n:loops|noisy|react|success_rate|%-->56%<!--/n--> and <!--n:loops|noisy|plan_execute|success_rate|%-->56%<!--/n-->), which is asserted in the tests.

**4. Route every model and tool call through one `Runtime`.**
Identical metering for all architectures, and tracing, journaling and replay for free. Evidence: replay reproduced the complete event stream, timestamps included, in <!--n:tracing|*|react|replay_identical|%-->100%<!--/n--> of recorded runs for all three loops.

**5. Implement reliability and security as wrappers, not as loop features.**
Retry, breaker, idempotency, permissions, journaling and crash injection are `ToolExecutor` wrappers; routing is a `Model` wrapper. The same ReAct loop (<!--n:complexity|*|react|sloc|0-->57<!--/n--> SLOC) is used unmodified in the recovery, memory, tools, permissions, routing and durability experiments.

**6. Offer durability both as snapshots and as a journal, and treat idempotency as mandatory with either.**
Journal recovery re-issued <!--n:durability|single crash (exhaustive)|journal|extra_model_calls_mean|2-->0.00<!--/n--> model calls per crash against <!--n:durability|single crash (exhaustive)|snapshot|extra_model_calls_mean|2-->1.00<!--/n--> for snapshots and <!--n:durability|single crash (exhaustive)|restart|extra_model_calls_mean|1-->7.0<!--/n--> for a restart, and wrote <!--n:durability|single crash (exhaustive)|journal|store_bytes_mean|k-->9.4k<!--/n--> bytes against <!--n:durability|single crash (exhaustive)|snapshot|store_bytes_mean|k-->49.0k<!--/n-->. Neither is exactly-once on its own: both completed <!--n:durability|single crash (exhaustive)|journal|success_rate|%-->88%<!--/n--> of crashed runs correctly without idempotency keys and <!--n:durability|single crash (exhaustive)|journal+idem|success_rate|%-->100%<!--/n--> with them.

**7. In the verified graph, verify before side effects rather than after every step.**
Auditing every step took <!--n:loops|noisy|verified_graph[all]|model_calls_mean|1-->15.8<!--/n--> model calls per task against <!--n:loops|noisy|verified_graph|model_calls_mean|1-->7.8<!--/n-->, for <!--n:loops|noisy|verified_graph[all]|success_rate|%-->96%<!--/n--> versus <!--n:loops|noisy|verified_graph|success_rate|%-->95%<!--/n--> success. Reads are cheap to redo; the gate belongs where mistakes become irreversible.

**8. Let code, not the model, schedule the supervisor's subtasks.**
The supervisor makes one decomposition call and one final call; dependency tracking, parallel dispatch and reassignment are deterministic code. That keeps coordination overhead to messages rather than model turns and makes failure handling testable.

**9. Retry transient faults below the model.**
Under 30% transient faults, model-mediated retry used <!--n:recovery|transient 30%|model-mediated|total_tokens_mean|k-->11.2k<!--/n--> tokens per task and runtime backoff <!--n:recovery|transient 30%|backoff|total_tokens_mean|k-->7.7k<!--/n-->. Errors the model can fix (bad arguments) still go to the model.

**10. Enforce authorization on arguments, outside the model.**
A tool-name allowlist let the injected call through in <!--n:permissions|model always obeys injected text|allowlist (tool names)|exfil_mean|%-->100%<!--/n--> of runs because the attack used a tool the task needs; an argument-scoped capability token let through <!--n:permissions|model always obeys injected text|capability token (argument-scoped)|exfil_mean|%-->0%<!--/n--> with no human requests.

**11. Keep one source of truth per fact and generate the rest.**
Pattern pages, the decision guide, the results page and the explorer's data are generated from `pattern.toml`, `guide.toml`, `sources.toml` and the result files; numbers in prose are bound to result rows; CI fails when anything is stale. A catalogue whose numbers drift from its code is worse than no catalogue.

**12. Use the official MCP SDKs on both sides of the interop example.**
The protocol's handshake and session model changed between the 2025-11-25 and 2026-07-28 revisions. Re-implementing the wire format would have aged immediately; the SDK-to-SDK test keeps working across revisions.

**13. Keep the explorer static and separate.**
It reads generated JSON and imports nothing from the library, so the catalogue can be hosted anywhere and the library carries no web dependencies.
