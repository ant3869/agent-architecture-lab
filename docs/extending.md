# Extending the catalogue

Three kinds of change, from smallest to largest. In every case the last two steps are the same: rebuild, then make the checks pass.

## A. Add a solution to an existing problem

1. **Implement it** in the matching package under `src/agentlab/`, against `Model` / `ToolExecutor` and through `Runtime`. If it is a policy, make it a wrapper. Standard library only.
2. **Add a runnable example** `examples/NN_name.py` that prints something a reader can check and ends with a goal check. Add it to the table in `examples/README.md`.
3. **Add tests** in `tests/`. Test the mechanism directly (state transitions, edge cases, error paths) and its effect end to end on a task. Include at least one failure scenario.
4. **Add it to the experiment** for that problem (`experiments/exp_<id>.py`): one more entry in the dictionary of architectures. Use the same tasks, seeds and fault plans as the alternatives. Add a finding only if it is computed from the rows.
5. **Describe it** in `patterns/<problem>/pattern.toml` as a new `[[solutions]]` table:

```toml
[[solutions]]
id = "my_solution"
name = "Readable name"
status = "implemented"
summary = "One or two sentences."
implementation = "src/agentlab/..."
example = "examples/NN_name.py"
tests = "tests/test_....py"
result_arch = ["label used in the experiment rows"]
diagram = '''
flowchart LR
  A --> B
'''
advantages = ["..."]
limitations = ["..."]
performance = "Measured: {{experiment|scenario|arch|key|fmt}} ..."
complexity = "..."
reliability = "..."
security = "..."
use_when = ["..."]
avoid_when = ["..."]
integration = """
Prose and a fenced code block.
"""
frameworks = "Where readers have met this idea."
```

A solution you describe but do not implement uses `status = "documented"` and omits the file fields.

6. **Regenerate results and pages.**

```bash
python -m experiments.run_all --perf
```

```bash
python scripts/build_catalog.py
```

7. **Run the checks.**

```bash
pytest
```

```bash
python scripts/build_catalog.py --check
```

## B. Add a new problem

Do everything in A, plus:

1. Create `patterns/<id>/pattern.toml` with the top-level fields `id`, `order`, `title`, `tagline`, `experiment`, `research`, `problem`, `applications`, `decision` and at least three `[[solutions]]`.
2. Create `experiments/exp_<id>.py` exposing `run(n) -> dict` built with `experiments.common.experiment(...)`: a question, the conditions, columns, rows, findings computed from the rows, and limitations. Register it in `EXPERIMENTS` in `experiments/run_all.py`.
3. Add the problem to `patterns/guide.toml` with a recommendation and bound evidence.
4. If it adds a research topic, write a section in `research/topics.md` and add its sources to `research/sources.toml` (see C).
5. Record a trace for the explorer in `scripts/record_traces.py` if a run is instructive to watch.

## C. Add or change a research claim

1. Fetch the source and read the passage you intend to cite.
2. Add an entry to `research/sources.toml` with `verified = "content"` and a `note` stating what you read. Use `"reachable"` only if you are citing from prior knowledge and say so.
3. Cite it in prose as `[label][key]`.
4. Run `python scripts/verify_sources.py` (needs network), then `python scripts/build_catalog.py`.

## Writing rules

- A finding is a sentence whose numbers are computed from result rows. A recommendation is advice and is labelled as such. Do not mix them.
- State an experiment's limitations next to its findings, especially where the simulator favours one alternative.
- Three solutions must differ in mechanism (who decides, where state lives, what is persisted), not in parameters.
- Prefer adding a scenario that breaks a pattern over adding one that confirms it.

## Extending the simulator

New error sources must be keyed draws from `core.util.u01` so noise stays paired, and the simulated model must stay stateless. If you add a model `mode`, document its contract in [`integration.md`](integration.md). If a change alters existing results, that is allowed, but regenerate and review every bound number: the build will tell you which pages changed.
