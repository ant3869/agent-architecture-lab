"""Contract tests for the Anthropic adapter against a stub client.

These verify request construction and response mapping. They do NOT call the live API.
"""
from types import SimpleNamespace as NS

import pytest

from agentlab.core.runtime import Runtime
from agentlab.core.types import Message, ModelRequest
from agentlab.integrations.anthropic_model import AnthropicModel, ModelError, tool_param
from agentlab.loops.react import ReActLoop
from agentlab.sim.tasks import evaluate, make_task
from agentlab.sim.world import WORLD_SPECS, World
from agentlab.tools.registry import StaticRegistry, world_tools


def usage(i=100, o=20, read=0, write=0):
    return NS(input_tokens=i, output_tokens=o, cache_read_input_tokens=read, cache_creation_input_tokens=write)


def tool_use(id, name, input):
    return NS(type="tool_use", id=id, name=name, input=input)


class ScriptedClient:
    """Plays back a fixed list of API responses and records every request."""

    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.messages = NS(create=self._create)
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def scripted_solution(task):
    """The API responses a competent model would give for `task`, with a thinking block on each turn."""
    out, values = [], {}
    world = World(task)
    for s in task.steps:
        args = {k: values[v.step] if hasattr(v, "step") else v for k, v in s.args.items()}
        values[s.id] = world.call(s.tool, args).output
        out.append(NS(model="claude-opus-5-5", stop_reason="tool_use", stop_details=None, usage=usage(), content=[NS(type="thinking", thinking="", signature="sig"), tool_use(f"toolu_{s.id}", s.tool, args)]))
    out.append(NS(model="claude-opus-5-5", stop_reason="end_turn", stop_details=None, usage=usage(), content=[NS(type="text", text="All done.")]))
    return out


def test_react_loop_runs_on_the_adapter_and_pairs_tool_results():
    task = make_task(2, stages=1, lookups=2)
    client = ScriptedClient(scripted_solution(task))
    world = World(task)
    rt = Runtime(AnthropicModel(client), StaticRegistry(world_tools(world)))
    result = ReActLoop(rt).run(task.goal_message())
    assert result.status == "final" and evaluate(task, world).success
    assert rt.meter.model_calls == len(task.steps) + 1 and rt.meter.prompt_tokens == 100 * rt.meter.model_calls
    last = client.requests[-1]["messages"]
    assert [m["role"] for m in last] == ["user"] + ["assistant", "user"] * len(task.steps)
    for assistant, user in zip(last[1::2], last[2::2]):
        assert assistant["content"][0].type == "thinking", "assistant turns are replayed exactly as returned"
        assert user["content"][0] == {"type": "tool_result", "tool_use_id": assistant["content"][1].id, "content": user["content"][0]["content"]}


def test_request_shape():
    client = ScriptedClient([NS(model="claude-opus-5-5", stop_reason="end_turn", stop_details=None, usage=usage(), content=[NS(type="text", text="ok")])])
    AnthropicModel(client).complete(ModelRequest("act", [Message("user", "hi")], [WORLD_SPECS["compute"]]))
    req = client.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["output_config"] == {"effort": "medium"} and req["max_tokens"] == 16000
    assert req["betas"] == ["server-side-fallback-2026-07-01"] and req["fallbacks"] == "default"
    assert req["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert req["tools"][0]["input_schema"]["properties"]["op"]["enum"] == ["add", "sub", "mul"]
    assert "thinking" not in req and "temperature" not in req
    plain = ScriptedClient([NS(model="m", stop_reason="end_turn", stop_details=None, usage=usage(), content=[])])
    AnthropicModel(plain, refusal_fallback=False).complete(ModelRequest("finalize", [Message("user", "hi")], [WORLD_SPECS["compute"]]))
    assert "betas" not in plain.requests[0] and "tools" not in plain.requests[0]
    assert tool_param(WORLD_SPECS["compute"], strict=True)["strict"] is True


def test_errors_memory_and_reconstruction_are_mapped():
    m = AnthropicModel(ScriptedClient([]))
    history = [
        Message("user", "goal"),
        Message("memory", "Memory: s1=3"),
        Message("assistant", "a", {"call": {"tool": "lookup", "args": {"key": "k"}, "step_id": "toolu_1", "idem_key": ""}}),
        Message("tool", "ERROR NOT_FOUND: no such key", {"step_id": "toolu_1", "ok": False}),
        Message("system", "Verifier rejected: s1"),
    ]
    api = m.to_api_messages(history)
    assert [x["role"] for x in api] == ["user", "assistant", "user"]
    assert [b["type"] for b in api[0]["content"]] == ["text", "text"]
    assert api[1]["content"] == [{"type": "tool_use", "id": "toolu_1", "name": "lookup", "input": {"key": "k"}}], "unknown turns are rebuilt from the call"
    assert api[2]["content"][0]["is_error"] is True and api[2]["content"][1]["type"] == "text"


def test_usage_cost_refusal_and_truncation():
    resp = NS(model="claude-opus-5-5", stop_reason="end_turn", stop_details=None, usage=usage(i=1000, o=500, read=4000, write=1000), content=[NS(type="text", text="x")])
    out = AnthropicModel(ScriptedClient([resp])).complete(ModelRequest("act", [Message("user", "hi")], []))
    assert (out.prompt_tokens, out.completion_tokens, out.final) == (6000, 500, True)
    assert out.cost == pytest.approx((6000 * 4.0 + 500 * 20.0) / 1e6) and out.data["cache_read_tokens"] == 4000
    refusal = NS(model="claude-opus-5-5", stop_reason="refusal", stop_details=NS(category="cyber", explanation="..."), usage=usage(), content=[])
    out = AnthropicModel(ScriptedClient([refusal])).complete(ModelRequest("act", [Message("user", "hi")], []))
    assert out.final and out.data["blocked"] and "cyber" in out.text
    cut = NS(model="claude-opus-5-5", stop_reason="max_tokens", stop_details=None, usage=usage(), content=[])
    with pytest.raises(ModelError, match="max_tokens"):
        AnthropicModel(ScriptedClient([cut])).complete(ModelRequest("act", [Message("user", "hi")], []))
    with pytest.raises(ModelError, match="does not implement mode 'plan'"):
        AnthropicModel(ScriptedClient([])).complete(ModelRequest("plan", [], []))


def test_sdk_errors_are_classified_as_retryable_or_not():
    anthropic = pytest.importorskip("anthropic")
    import httpx2 as httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def failing(exc):
        def create(**kwargs):
            raise exc

        return NS(messages=NS(create=create), beta=NS(messages=NS(create=create)))

    req = ModelRequest("act", [Message("user", "hi")], [])
    for status, cls, retryable in ((429, anthropic.RateLimitError, True), (400, anthropic.BadRequestError, False), (529, anthropic.InternalServerError, True)):
        exc = cls("boom", response=httpx.Response(status, request=request), body=None)
        with pytest.raises(ModelError) as info:
            AnthropicModel(failing(exc)).complete(req)
        assert info.value.retryable is retryable
    with pytest.raises(ModelError) as info:
        AnthropicModel(failing(anthropic.APIConnectionError(request=request))).complete(req)
    assert info.value.retryable
