from agentlab.core.types import ToolCall
from agentlab.eval.harness import run_loop, setup
from agentlab.sim.model import ModelProfile
from agentlab.sim.tasks import make_task
from agentlab.sim.world import WORLD_SPECS
from agentlab.tools.registry import LazyRegistry, ScopedRegistry, StaticRegistry, distractor_tools, validate_args, world_tools

T = make_task(1, stages=2, lookups=3)


def catalogue(world):
    return world_tools(world) + distractor_tools(35)


def test_static_registry_exposes_everything_and_validates_nothing():
    s = setup(T, wrap=lambda t, w: StaticRegistry(catalogue(w)))
    assert len(s.tools.specs()) == 39
    assert s.tools.execute(ToolCall("nope", {})).error_code == "UNKNOWN_TOOL"
    assert s.tools.execute(ToolCall("compute", {"op": "pow", "a": 1, "b": 2})).error_code == "INVALID_OP"
    assert len(s.world.calls) == 1, "the malformed call reached the backend"


def test_schema_validation_covers_shape_type_enum_and_pattern():
    spec = WORLD_SPECS["compute"]
    assert validate_args(spec, {"op": "add", "a": 1, "b": 2.5}) == ""
    assert "missing=['b']" in validate_args(spec, {"op": "add", "a": 1})
    assert "unexpected=['c']" in validate_args(spec, {"op": "add", "a": 1, "b": 2, "c": 3})
    assert "must be a number" in validate_args(spec, {"op": "add", "a": "1", "b": 2})
    assert "must be a number" in validate_args(spec, {"op": "add", "a": True, "b": 2})
    assert "one of" in validate_args(spec, {"op": "pow", "a": 1, "b": 2})
    assert "does not match" in validate_args(WORLD_SPECS["write"], {"key": "!x", "value": 1})
    schema = spec.json_schema()
    assert schema["properties"]["op"] == {"type": "string", "enum": ["add", "sub", "mul"]} and schema["additionalProperties"] is False


def test_scoped_registry_rejects_before_the_backend_and_only_narrows():
    s = setup(T, wrap=lambda t, w: ScopedRegistry(catalogue(w), ["data", "math", "ops"]))
    assert sorted(x.name for x in s.tools.specs()) == ["compute", "lookup", "send", "write"]
    assert s.tools.execute(ToolCall("compute", {"op": "pow", "a": 1, "b": 2})).error_code == "INVALID_ARGS"
    assert s.tools.execute(ToolCall("crm_get_contact", {"resource_id": "1", "filters": None, "limit": 1})).error_code == "UNKNOWN_TOOL"
    assert s.tools.rejected == 2 and s.world.calls == []
    math = s.tools.scope(["math"])
    assert [x.name for x in math.specs()] == ["compute"]
    assert [x.name for x in math.scope(["math", "ops", "crm"]).specs()] == ["compute"]


def test_lazy_registry_discloses_progressively():
    s = setup(T, wrap=lambda t, w: LazyRegistry(catalogue(w)))
    reg = s.tools
    assert [x.name for x in reg.specs()] == ["search_tools"]
    assert reg.execute(ToolCall("lookup", {"key": "k"})).error_code == "UNKNOWN_TOOL"
    assert reg.execute(ToolCall("search_tools", {"query": 7})).error_code == "INVALID_ARGS"
    assert reg.execute(ToolCall("search_tools", {"query": "data"})).output == ["lookup"]
    assert [x.name for x in reg.specs()] == ["search_tools", "lookup"]
    assert reg.execute(ToolCall("lookup", {"key": T.steps[0].args["key"]})).ok
    assert len(reg.search("billing")) == 4, "top_k caps how many schemas one search may load"


def test_all_registries_complete_the_task_and_differ_in_prompt_cost():
    rows = {}
    for name, mk in {"static": lambda c: StaticRegistry(c), "scoped": lambda c: ScopedRegistry(c, ["data", "math", "ops"]), "lazy": lambda c: LazyRegistry(c)}.items():
        rows[name] = run_loop("react", T, ModelProfile(slip_rate=0.1, silent_fraction=0.0), seed=2, wrap=lambda t, w, mk=mk: mk(catalogue(w)))
        assert rows[name]["success"]
    assert rows["scoped"]["prompt_tokens"] < rows["lazy"]["prompt_tokens"] < rows["static"]["prompt_tokens"] / 2
    assert rows["lazy"]["model_calls"] == rows["static"]["model_calls"] + 3, "one discovery call per capability"


def test_distractors_are_inert_and_bounded():
    d = distractor_tools(35)
    assert len(d) == 35 and len({t.spec.name for t in d}) == 35
    assert d[0].fn(ToolCall(d[0].spec.name, {})).error_code == "NOT_APPLICABLE"
