"""The published numbers must be reproducible bit-for-bit."""
import json
from pathlib import Path

import pytest

from experiments import exp_complexity, exp_loops, exp_permissions, run_all

RESULTS = Path(__file__).resolve().parents[1] / "experiments" / "results"


def test_experiments_are_deterministic():
    a, b = run_all.run_all(12), run_all.run_all(12)
    assert run_all.digest(a) == run_all.digest(b)
    assert set(a) == {"loops", "orchestration", "durability", "recovery", "memory", "routing", "tools", "permissions", "tracing", "complexity"}


def test_every_experiment_states_conditions_findings_and_limitations():
    for r in run_all.run_all(12).values():
        assert r["question"] and r["conditions"] and len(r["findings"]) >= 3 and len(r["limitations"]) >= 2
        keys = {c["key"] for c in r["columns"]}
        assert all(keys & set(row) for row in r["rows"])
        assert all(g in row for row in r["rows"] for g in r["group_by"])


@pytest.mark.skipif(not (RESULTS / "manifest.json").exists(), reason="results not generated yet: run `python -m experiments.run_all`")
@pytest.mark.parametrize("module", [exp_loops, exp_permissions, exp_complexity], ids=lambda m: m.__name__.split(".")[-1])
def test_committed_results_match_a_fresh_run(module):
    manifest = json.loads((RESULTS / "manifest.json").read_text())
    fresh = module.run(manifest["n"])
    committed = json.loads((RESULTS / f"{fresh['id']}.json").read_text())
    assert json.loads(json.dumps(fresh)) == committed, "re-run `python -m experiments.run_all` and commit the results"


@pytest.mark.skipif(not (RESULTS / "manifest.json").exists(), reason="results not generated yet")
def test_results_markdown_is_in_sync_with_the_json():
    manifest = json.loads((RESULTS / "manifest.json").read_text())
    results = {rid: json.loads((RESULTS / f"{rid}.json").read_text()) for rid in manifest["experiments"]}
    assert run_all.digest(results) == manifest["digest"]
    md = (RESULTS.parent / "RESULTS.md").read_text()
    assert md == run_all.markdown(results, manifest["n"], manifest["digest"])
