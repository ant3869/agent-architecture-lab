"""E9 - implementation complexity, measured from the source with `ast`."""
from __future__ import annotations

import ast
from pathlib import Path

from .common import experiment

ROOT = Path(__file__).resolve().parents[1] / "src" / "agentlab"
FILES = {
    "execution loops": {"react": "loops/react.py", "plan_execute": "loops/plan_execute.py", "verified_graph": "loops/verified_graph.py", "(graph engine)": "statemachine/graph.py"},
    "orchestration": {"supervisor-worker": "orchestration/supervisor.py", "peer handoff": "orchestration/handoff.py", "(message bus)": "orchestration/bus.py"},
    "durability": {"snapshot store + journal store": "durability/stores.py", "journal replay": "durability/journal.py"},
    "middleware": {"retry / breaker / idempotency": "recovery/policies.py", "permissions": "permissions/policy.py", "routers": "routing/router.py", "context policies": "memory/context.py", "tool registries": "tools/registry.py"},
}
BRANCH = (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler, ast.BoolOp, ast.IfExp, ast.comprehension, ast.With, ast.Match)


def measure(path: Path) -> dict:
    src = path.read_text()
    tree = ast.parse(src)
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node, clean=False) is not None:
            d = node.body[0]
            doc_lines.update(range(d.lineno, d.end_lineno + 1))
    sloc = sum(1 for i, line in enumerate(src.splitlines(), 1) if line.strip() and not line.strip().startswith("#") and i not in doc_lines)
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return {
        "sloc": sloc,
        "branch_points": sum(isinstance(n, BRANCH) for n in ast.walk(tree)),
        "functions": len(funcs),
        "classes": sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree)),
        "longest_function": max((f.end_lineno - f.lineno + 1 for f in funcs), default=0),
    }


def run(n: int = 0) -> dict:
    rows = []
    for group, files in FILES.items():
        for name, rel in files.items():
            rows.append({"scenario": group, "arch": name, "file": f"src/agentlab/{rel}", **measure(ROOT / rel)})
    by = {r["arch"]: r for r in rows}
    findings = [
        f"ReAct is the smallest loop ({by['react']['sloc']} SLOC, {by['react']['branch_points']} branch points); plan-and-execute is {by['plan_execute']['sloc']} SLOC; "
        f"the verified graph is {by['verified_graph']['sloc']} SLOC plus a {by['(graph engine)']['sloc']}-SLOC graph engine it depends on.",
        f"Supervisor-worker is {by['supervisor-worker']['sloc']} SLOC with {by['supervisor-worker']['branch_points']} branch points; peer handoff is {by['peer handoff']['sloc']} SLOC with {by['peer handoff']['branch_points']}.",
        f"Journal replay adds {by['journal replay']['sloc']} SLOC and wraps any loop unchanged; snapshot checkpointing needs a hook inside each loop instead.",
    ]
    return experiment(
        "complexity",
        "Implementation complexity",
        "How much code and branching does each pattern cost to own?",
        {"method": "Python ast; SLOC excludes blank lines, comments and docstrings; branch points = if/for/while/try/except/with/match/boolean-op/conditional-expression/comprehension nodes"},
        [("arch", "Implementation"), ("file", "File"), ("sloc", "SLOC"), ("branch_points", "Branch points"), ("functions", "Functions"), ("classes", "Classes"), ("longest_function", "Longest function (lines)")],
        ["scenario"],
        rows,
        findings,
        ["Size of a reference implementation, not of a production system: no async I/O, streaming, auth or schema migration.", "Shared infrastructure (runtime, tracer, simulator) is excluded from every row."],
    )
