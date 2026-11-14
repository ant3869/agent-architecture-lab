"""Cross-language interop: unmodified Python loops drive tools served by the TypeScript MCP server."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentlab.core.runtime import Runtime
from agentlab.core.types import ToolCall
from agentlab.eval.harness import LOOPS
from agentlab.recovery.policies import IdempotentTools
from agentlab.sim.model import ModelProfile, SimModel
from agentlab.sim.tasks import evaluate, make_task

SERVER = Path(__file__).resolve().parents[1] / "integrations" / "mcp-tool-server" / "dist" / "server.js"
pytest.importorskip("mcp", reason='install the optional extra: pip install "agentlab[mcp]"')
pytestmark = [
    pytest.mark.interop,
    pytest.mark.skipif(shutil.which("node") is None or not SERVER.exists(), reason="build the server first: cd integrations/mcp-tool-server && npm install && npm run build"),
]

from agentlab.integrations.mcp_tools import MCPToolset  # noqa: E402


@pytest.fixture
def served(tmp_path):
    task = make_task(3, stages=2, lookups=2, moved=1)
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"kv": task.kv, "moved": task.moved, "recipients": ["ops", "audit"]}))
    with MCPToolset("node", [str(SERVER), str(seed)], hidden={"dump_state"}) as tools:
        yield task, tools


def remote_world(tools):
    _, data = tools.call_raw("dump_state", {})
    state = data["output"]
    return SimpleNamespace(writes=[tuple(w) for w in state["writes"]], outbox=[tuple(o) for o in state["outbox"]])


def test_tool_discovery_maps_schemas_and_risk_annotations(served):
    _, tools = served
    specs = {s.name: s for s in tools.specs()}
    assert set(specs) == {"lookup", "compute", "write", "send"}, "dump_state is hidden from the model"
    assert specs["compute"].params == {"op": "string", "a": "number", "b": "number"}
    assert [specs[n].effect for n in ("lookup", "compute", "write", "send")] == ["read", "read", "write", "external"]
    assert specs["send"].idempotent is False and specs["write"].idempotent is True
    assert specs["lookup"].domain == "data" and "idempotency_key" not in specs["send"].params


def test_errors_cross_the_boundary_as_typed_tool_results(served):
    task, tools = served
    old = next(iter(task.moved))
    r = tools.execute(ToolCall("lookup", {"key": old}))
    assert (r.ok, r.error_code, r.info) == (False, "MOVED", {"moved_to": task.moved[old]})
    assert tools.execute(ToolCall("compute", {"op": "pow", "a": 1, "b": 2})).error_code == "INVALID_OP"
    assert tools.execute(ToolCall("send", {"to": "nobody", "body": 1})).error_code == "UNKNOWN_RECIPIENT"
    assert tools.execute(ToolCall("dump_state", {})).error_code == "UNKNOWN_TOOL"
    bad_type = tools.execute(ToolCall("compute", {"op": "add", "a": "one", "b": 2}))
    assert not bad_type.ok, "the server SDK rejects arguments that violate the declared schema"


@pytest.mark.parametrize("loop", LOOPS)
def test_python_loops_complete_a_task_against_the_typescript_server(served, loop):
    task, tools = served
    rt = Runtime(SimModel(ModelProfile(slip_rate=0.1, silent_fraction=0.0), task, seed=4), tools)
    result = LOOPS[loop](rt).run(task.goal_message())
    assert result.status == "final"
    assert evaluate(task, remote_world(tools)).success


def test_idempotency_keys_are_honoured_across_the_protocol(served):
    task, tools = served
    keyed = IdempotentTools(tools, "run-1")
    call = ToolCall("send", {"to": "ops", "body": 7}, "s9")
    first, second = keyed.execute(call), keyed.execute(call)
    assert first.ok and second.ok and second.deduped and not first.deduped
    tools.execute(call)
    assert remote_world(tools).outbox == [("ops", 7), ("ops", 7)], "two effects: one keyed (collapsed twice into one), one unkeyed"


def test_a_missing_server_fails_fast_with_a_clear_error():
    from agentlab.integrations.mcp_tools import MCPConnectionError

    with pytest.raises(MCPConnectionError, match="could not start MCP server"):
        MCPToolset("node", ["/nonexistent/server.js"], timeout_s=5)
