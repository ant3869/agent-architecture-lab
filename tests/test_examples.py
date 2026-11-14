"""Every example must run on its own, from a clean interpreter, and end in a passing goal check."""
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = sorted((Path(__file__).resolve().parents[1] / "examples").glob("[0-9]*.py"))


def test_there_is_an_example_for_every_required_implementation():
    assert len(EXAMPLES) == 13


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_runs(path):
    proc = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip() and "Traceback" not in proc.stdout
