"""The catalogue's guarantees: complete entries, resolvable citations, nothing stale."""
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = sorted((ROOT / "patterns").glob("*/pattern.toml"))
SOURCES = {s["key"]: s for s in tomllib.loads((ROOT / "research" / "sources.toml").read_text())["source"]}
REQUIRED = ("id", "name", "status", "summary", "advantages", "limitations", "use_when", "avoid_when", "frameworks")


def test_generated_artefacts_are_up_to_date():
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_catalog.py"), "--check"], capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, f"run `python scripts/build_catalog.py`\n{proc.stdout}{proc.stderr}"


def test_initial_scope_is_covered():
    by_id = {p.parent.name: tomllib.loads(p.read_text()) for p in PATTERNS}
    implemented = lambda pid: [s["id"] for s in by_id[pid]["solutions"] if s["status"] == "implemented"]
    assert len(by_id) >= 9
    assert len(implemented("execution-loops")) >= 3, "three contrasting execution loops"
    assert {"supervisor", "handoff"} <= set(implemented("orchestration")), "two orchestration architectures"
    for pid, p in by_id.items():
        assert len(p["solutions"]) >= 3, f"{pid}: each problem documents at least three solutions"
        assert len(implemented(pid)) >= 3, f"{pid}: at least three are implemented"


@pytest.mark.parametrize("path", PATTERNS, ids=lambda p: p.parent.name)
def test_pattern_entry_is_complete(path):
    p = tomllib.loads(path.read_text())
    assert p["id"] == path.parent.name
    for field in ("title", "tagline", "problem", "applications", "decision", "experiment", "research"):
        assert p[field], f"{p['id']}: missing {field}"
    assert all(k in SOURCES for k in p["research"])
    assert any(s.get("diagram") for s in p["solutions"]), "every problem has at least one architecture diagram"
    for s in p["solutions"]:
        for field in REQUIRED:
            assert s.get(field), f"{p['id']}/{s.get('id')}: missing {field}"
        if s["status"] == "implemented":
            for field in ("implementation", "example", "tests"):
                assert (ROOT / s[field]).is_file(), f"{p['id']}/{s['id']}: {field} does not exist"
            assert s.get("result_arch"), f"{p['id']}/{s['id']}: implemented solutions are tied to measured results"
            assert s.get("performance") or s.get("reliability"), f"{p['id']}/{s['id']}: needs a measured statement"
        else:
            assert s["status"] == "documented" and "implementation" not in s


def test_every_citation_resolves_and_every_source_is_classified():
    for md in [*ROOT.glob("research/*.md"), *ROOT.glob("docs/*.md"), ROOT / "README.md"]:
        text = md.read_text()
        body = re.sub(r"```.*?```|`[^`\n]*`", "", text.split("<!-- refs:start -->")[0], flags=re.S)
        for key in re.findall(r"\]\[([a-z0-9-]+)\]", body):
            assert key in SOURCES, f"{md.name}: unknown citation key {key}"
            assert f"[{key}]: {SOURCES[key]['url']}" in text, f"{md.name}: missing link definition for {key}; rebuild"
    for s in SOURCES.values():
        assert s["verified"] in ("content", "reachable", "unverified") and s["note"] and s["url"].startswith("https://")
    cited = set(re.findall(r"\]\[([a-z0-9-]+)\]", (ROOT / "research" / "topics.md").read_text() + (ROOT / "research" / "frameworks.md").read_text()))
    assert len(cited) >= 40, "the research notes should lean on the bibliography"


def test_numbers_in_prose_are_bound_to_results():
    """Hand-written pages that quote measurements must use bound markers, which the build keeps current."""
    for name in ("README.md", "docs/engineering-decisions.md", "research/topics.md"):
        text = (ROOT / name).read_text()
        assert len(re.findall(r"<!--n:[^>]+-->[^<]+<!--/n-->", text)) >= 10, f"{name}: expected bound numbers"
        assert "<!--n:" not in text or "-->?<!--/n-->" not in text, f"{name}: unresolved number marker; run the build"


def test_explorer_data_matches_catalogue():
    import json

    data = json.loads((ROOT / "explorer" / "public" / "data" / "catalog.json").read_text())
    assert [p["id"] for p in data["patterns"]] == [p["id"] for p in sorted((tomllib.loads(x.read_text()) for x in PATTERNS), key=lambda p: p["order"])]
    assert "{{" not in json.dumps(data["patterns"]) and "{{" not in json.dumps(data["guide"]), "unresolved placeholders"
    for t in data["traces"]:
        assert (ROOT / "explorer" / "public" / "data" / "traces" / f"{t['id']}.json").is_file()
    for p in data["patterns"]:
        for s in p["solutions"]:
            if s["status"] == "implemented":
                assert s["implementation"] in data["code"] and s["example"] in data["code"]
