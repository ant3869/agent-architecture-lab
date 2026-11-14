# Experiments

Ten experiments that run competing implementations through identical scenarios. Results are in [`RESULTS.md`](RESULTS.md) (generated) and [`results/`](results) (one JSON file per experiment plus a manifest with a digest).

| Module | Compares | Scenarios |
|---|---|---|
| `exp_loops.py` | ReAct, Plan-and-Execute, verified graph (two verification policies) | clean, surprises, 8% slips, both, long tasks |
| `exp_orchestration.py` | single agent, supervisor (1 and 3 workers per skill), peer handoff | 15 / 29 / 57 steps; an agent crash at four positions |
| `exp_durability.py` | restart, snapshot, graph checkpoint, journal, each with and without idempotency keys | a crash at every tool-call boundary; two crashes in one run |
| `exp_recovery.py` | model-mediated retry, backoff, breaker with fallback, with and without idempotency keys | transient faults, sustained outage, lost replies |
| `exp_memory.py` | full history, three window sizes, compaction, fact ledger | 15 / 29 / 57 steps |
| `exp_routing.py` | all-small, all-large, role, cascade, cascade with a small verifier | on each of the three loops |
| `exp_tools.py` | static, scoped, lazy registries | 39-tool catalogue; perfect model and 10% malformed calls |
| `exp_permissions.py` | none, allowlist, approval (attentive and rubber-stamp reviewer), capability token | injected exfiltration at two susceptibility levels |
| `exp_tracing.py` | event log, span tree, replay | each loop |
| `exp_complexity.py` | source size and branching of each implementation | static analysis |

## Running

Quick look (prints findings, writes nothing):

```bash
python -m experiments.run_all --n 40
```

Regenerate the published results (n = 200) and machine-dependent timings:

```bash
python -m experiments.run_all --perf
```

Then refresh the pages and explorer data that embed them:

```bash
python scripts/build_catalog.py
```

## Rules

- An experiment module exposes `run(n) -> dict` and builds its result with `common.experiment(...)`.
- Every alternative in a comparison gets the same tasks, seeds and fault plans.
- Findings are f-strings computed from the result rows, never typed numbers.
- Each experiment states its own limitations.
- No wall-clock time, randomness or I/O: results must be identical on every run. `perf.json` is the only machine-dependent output and is excluded from the digest.
