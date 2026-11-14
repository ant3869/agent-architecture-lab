"""The state-graph engine on its own: nodes, a router, per-node checkpoints and an interrupt.

No model involved. A document moves draft -> review -> (approve | revise) -> publish,
pausing at `review` until a human decision is supplied on resume.

Run:  python examples/06_state_graph.py
"""
from agentlab.core.types import Interrupt
from agentlab.durability.stores import SQLiteCheckpointer
from agentlab.statemachine.graph import END, StateGraph


def draft(s):
    return {"text": f"draft v{s['version'] + 1}", "version": s["version"] + 1}


def review(s):
    if s.get("decision") is None:
        raise Interrupt({"reason": "needs_review", "text": s["text"]})
    return {"last_decision": s["decision"], "decision": None}


def publish(s):
    return {"published": s["text"]}


g = StateGraph()
g.add_node("draft", draft).add_edge("draft", "review")
g.add_node("review", review).add_router("review", lambda s: "publish" if s["last_decision"] == "approve" else "draft")
g.add_node("publish", publish).add_edge("publish", END)
g.set_entry("draft")

store = SQLiteCheckpointer()
app = g.compile(store, on_transition=lambda a, b: print(f"  {a} -> {b}"))

state = app.run({"version": 0, "decision": None}, thread_id="doc-1")
print("paused:", state["__interrupt__"])
state = app.resume("doc-1", {"decision": "revise"})
print("paused:", state["__interrupt__"])
state = app.resume("doc-1", {"decision": "approve"})
print("published:", state["published"], "| checkpoints written:", store.writes)
