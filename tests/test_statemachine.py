import pytest

from agentlab.core.types import Interrupt
from agentlab.durability.stores import SQLiteCheckpointer
from agentlab.statemachine.graph import END, GraphError, StateGraph


def counter_graph(limit=3):
    g = StateGraph()
    g.add_node("inc", lambda s: {"n": s["n"] + 1}).add_router("inc", lambda s: END if s["n"] >= limit else "inc")
    return g.set_entry("inc")


def test_runs_to_end_and_checkpoints_every_node():
    store = SQLiteCheckpointer()
    out = counter_graph().compile(store).run({"n": 0}, "t")
    assert out["n"] == 3
    hist = store.history("t")
    assert [h["state"]["n"] for h in hist] == [1, 2, 3] and hist[-1]["next"] == END


def test_compile_rejects_malformed_graphs():
    with pytest.raises(GraphError, match="entry"):
        StateGraph().compile()
    g = StateGraph().add_node("a", lambda s: None).set_entry("a")
    with pytest.raises(GraphError, match="without outgoing"):
        g.compile()
    g.add_edge("a", "ghost")
    with pytest.raises(GraphError, match="unknown node"):
        g.compile()
    with pytest.raises(GraphError, match="duplicate"):
        g.add_node("a", lambda s: None)


def test_bad_router_and_runaway_graphs_are_caught():
    g = StateGraph().add_node("a", lambda s: None).add_router("a", lambda s: "ghost").set_entry("a")
    with pytest.raises(GraphError, match="unknown node 'ghost'"):
        g.compile().run({})
    with pytest.raises(GraphError, match="did not terminate"):
        counter_graph(limit=10**9).compile().run({"n": 0}, max_steps=50)


def test_interrupt_pauses_and_resume_reexecutes_the_node_from_its_start():
    entered = []

    def gate(s):
        entered.append(s.get("approved"))
        if not s.get("approved"):
            raise Interrupt({"reason": "need approval"})
        return {"done": True}

    g = StateGraph().add_node("prep", lambda s: {"prepared": True}).add_edge("prep", "gate")
    g.add_node("gate", gate).add_edge("gate", END).set_entry("prep")
    store = SQLiteCheckpointer()
    app = g.compile(store)
    paused = app.run({}, "t")
    assert paused["__interrupt__"] == {"node": "gate", "reason": "need approval"} and "done" not in paused
    final = app.resume("t", {"approved": True})
    assert final["done"] and "__interrupt__" not in final
    assert entered == [None, True], "the interrupted node ran twice: once to pause, once from the top on resume"
    assert app.resume("t")["done"], "resuming a finished thread returns its final state"


def test_resume_needs_a_checkpointer_and_a_known_thread():
    with pytest.raises(GraphError, match="requires a checkpointer"):
        counter_graph().compile().resume("t")
    with pytest.raises(GraphError, match="no checkpoint"):
        counter_graph().compile(SQLiteCheckpointer()).resume("missing")


def test_threads_are_isolated():
    store = SQLiteCheckpointer()
    app = counter_graph().compile(store)
    app.run({"n": 0}, "a")
    app.run({"n": 2}, "b")
    assert len(store.history("a")) == 3 and len(store.history("b")) == 1


def test_interrupt_in_the_entry_node_is_resumable():
    def first(s):
        if not s.get("go"):
            raise Interrupt({"reason": "wait"})
        return {"ran": True}

    g = StateGraph().add_node("first", first).add_edge("first", END).set_entry("first")
    app = g.compile(SQLiteCheckpointer())
    assert "__interrupt__" in app.run({}, "t")
    assert app.resume("t", {"go": True})["ran"]
