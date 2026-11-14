# Methodology

How the comparisons in this repository are produced, what each metric means, and where the line between measurement and opinion is drawn.

## Why a simulator

Comparing architectures on a live model confounds three things: the architecture, the model's behaviour on that day, and luck. To isolate the architecture this repository replaces the model and the environment with deterministic stand-ins and injects errors at controlled rates. The price is external validity, discussed in [`limitations.md`](limitations.md). The benefit is that every number is reproducible to the byte and differences between architectures are not noise.

## The task world

[`sim/tasks.py`](../src/agentlab/sim/tasks.py) generates tasks as dependency-ordered tool steps:

- **reads** (`lookup`) return values that are not in the task description and can only be obtained by calling the tool;
- **computations** (`compute`) combine earlier results;
- **effects** (`write`, idempotent; `send`, not idempotent) are irreversible and come last in each stage.

A task with *S* stages and *k* lookups per stage has 2*kS* + *S* + 1 steps when *S* ≥ 2 (15, 29 and 57 for 2, 4 and 8 stages of 3). Stages are independent of one another, which is what makes parallel delegation possible. Optional features: relocated keys (a surprise that returns a typed `MOVED` error), per-stage notifications (more non-idempotent effects), and a poisoned record carrying an injected instruction.

**Success** is decided by [`evaluate`](../src/agentlab/sim/tasks.py) on the final world state: every expected write holds the expected value, nothing unexpected was written, and the outbox equals the expected notifications as a multiset. Failures are typed: `wrong_effect`, `duplicate_effect`, `incomplete`, `exfiltration`. What the agent says about its own success is ignored.

## The simulated model

[`sim/model.py`](../src/agentlab/sim/model.py) is built on four rules.

1. **Competence is fixed, knowledge is not.** The model knows the structure of the solution but must find every concrete value in the messages it is given. If a context policy drops an observation, the model has to fetch it again. The sliding-window livelock in the memory experiment is not scripted; it emerges from this rule.
2. **Statelessness.** A response is a pure function of (seed, profile, request). Crash recovery, replay and context policies cannot leak hidden state through the model.
3. **Paired noise.** Whether a call is corrupted is drawn from a hash of (seed, task, step, attempt). Every architecture meets the same slips on the same steps, and a model with a lower slip rate fails on a subset of the calls a worse one fails on.
4. **Two kinds of error.** A *loud* slip makes the tool return an error. A *silent* slip is a valid call with the wrong meaning (a neighbouring key, a different operation, a wrong recipient); no tool reports it. The split is the `silent_fraction` parameter.

A verifier is modelled as an independent check that overlooks a wrong call with probability `verifier_miss_rate`.

## Faults

- **Tool faults** ([`sim/world.py`](../src/agentlab/sim/world.py)): seeded transient errors, outage windows on the simulated clock, and *ambiguous* failures where the effect is applied and the reply is lost.
- **Crashes** ([`durability/crash.py`](../src/agentlab/durability/crash.py)): the agent process dies immediately before or immediately after the *n*-th tool call. The durability experiment enumerates every *n* and both phases.
- **Agent crashes** in orchestration: a named agent dies right after its *k*-th tool call.

## Metrics

| Metric | Definition |
|---|---|
| Success rate | Share of runs whose final world state passes `evaluate`. Reported with a 95% Wilson interval in `RESULTS.md` and chart tooltips. |
| Model calls | Calls that reached a model. Calls served from a journal or tape are counted separately. |
| Tool calls / backend calls | Calls issued by the loop / calls that reached the world (includes runtime retries and fallbacks). |
| Tokens | Prompt plus completion tokens, estimated as characters / 4 over the actual message and tool-schema text. |
| Peak context | Largest single prompt in the run. |
| Cost | Tokens priced by the profile of the model that served each call, in abstract units. |
| Simulated time | Virtual milliseconds: fixed latencies per model and tool call, timeouts and backoff waits. |
| Makespan | Wall-clock under a virtual-time schedule of workers (orchestration only). |
| Duplicate effects | Non-idempotent effects applied more often than the reference solution requires. |
| Store bytes / writes | Bytes and rows written to the durable store. |
| SLOC, branch points | From Python's `ast`; see [`experiments/exp_complexity.py`](../experiments/exp_complexity.py). |

Wall-clock time and memory of the harness itself are recorded in `experiments/results/perf.json`. They are machine-dependent, excluded from the reproducibility digest and reported separately.

## Reproducibility

`python -m experiments.run_all` writes one JSON file per experiment, a manifest with a SHA-256 digest over all of them, and `RESULTS.md`. The test suite runs the experiments twice and compares digests, re-runs three experiments at full size and compares them with the committed files, and checks that `RESULTS.md` is exactly what the committed JSON renders to. `scripts/build_catalog.py --check` verifies that every generated page and every number embedded in hand-written prose matches the committed results.

## Measured versus recommended

- **Measured**: experiment tables, "Measured findings" lists, and any number in prose (each is bound to a result row by the build).
- **Recommended**: the "Recommendation" section of each pattern, "Use when / Avoid when" lists, and the "Recommendation" line of each decision-guide entry. These are the authors' engineering judgement, informed by the measurements and by the cited literature.
- **Cited**: claims about external systems and papers, each linked to a source whose verification status is recorded in [`research/SOURCES.md`](../research/SOURCES.md).

Each experiment lists its own limitations next to its findings.
