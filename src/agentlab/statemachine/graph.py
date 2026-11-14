"""A minimal explicit state-graph engine with per-node checkpoints and interrupts.

Semantics (deliberately close to LangGraph's documented behaviour):
* a node is `fn(state) -> dict | None`; the returned dict is shallow-merged into state;
* after every node the engine persists `{next, state}` under the run's thread id;
* a node may raise `Interrupt`; the run pauses with `next` pointing at that same node,
  so on resume the node **re-executes from its beginning**.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol

from ..core.types import Interrupt

END = "__end__"
Node = Callable[[dict[str, Any]], "dict[str, Any] | None"]
Router = Callable[[dict[str, Any]], str]


class Checkpointer(Protocol):
    def put(self, thread_id: str, payload: dict[str, Any]) -> int: ...

    def latest(self, thread_id: str) -> dict[str, Any] | None: ...


class GraphError(RuntimeError):
    pass


class StateGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, str | Router] = {}
        self.entry: str | None = None

    def add_node(self, name: str, fn: Node) -> "StateGraph":
        if name == END or name in self.nodes:
            raise GraphError(f"invalid or duplicate node name: {name}")
        self.nodes[name] = fn
        return self

    def add_edge(self, src: str, dst: str) -> "StateGraph":
        self.edges[src] = dst
        return self

    def add_router(self, src: str, router: Router) -> "StateGraph":
        self.edges[src] = router
        return self

    def set_entry(self, name: str) -> "StateGraph":
        self.entry = name
        return self

    def compile(self, checkpointer: Checkpointer | None = None, on_transition: Callable[[str, str], None] | None = None) -> "CompiledGraph":
        if self.entry not in self.nodes:
            raise GraphError("entry node is not defined")
        for src, dst in self.edges.items():
            if src not in self.nodes:
                raise GraphError(f"edge from unknown node: {src}")
            if isinstance(dst, str) and dst != END and dst not in self.nodes:
                raise GraphError(f"edge to unknown node: {dst}")
        missing = [n for n in self.nodes if n not in self.edges]
        if missing:
            raise GraphError(f"nodes without outgoing edge: {missing}")
        return CompiledGraph(self, checkpointer, on_transition)


class CompiledGraph:
    def __init__(self, graph: StateGraph, checkpointer: Checkpointer | None, on_transition: Callable[[str, str], None] | None):
        self.g = graph
        self.cp = checkpointer
        self.on_transition = on_transition

    def run(self, state: dict[str, Any], thread_id: str = "default", max_steps: int = 10_000) -> dict[str, Any]:
        assert self.g.entry is not None
        return self._drive(dict(state), self.g.entry, thread_id, max_steps)

    def resume(self, thread_id: str, update: dict[str, Any] | None = None, max_steps: int = 10_000) -> dict[str, Any]:
        if self.cp is None:
            raise GraphError("resume requires a checkpointer")
        saved = self.cp.latest(thread_id)
        if saved is None:
            raise GraphError(f"no checkpoint for thread {thread_id!r}")
        state = dict(saved["state"])
        state.pop("__interrupt__", None)
        state.update(update or {})
        if saved["next"] == END:
            return state
        return self._drive(state, saved["next"], thread_id, max_steps)

    def _save(self, thread_id: str, nxt: str, state: dict[str, Any]) -> None:
        if self.cp is not None:
            self.cp.put(thread_id, {"next": nxt, "state": state})

    def _drive(self, state: dict[str, Any], node: str, thread_id: str, max_steps: int) -> dict[str, Any]:
        for _ in range(max_steps):
            if node == END:
                return state
            try:
                update = self.g.nodes[node](state)
            except Interrupt as itr:
                state["__interrupt__"] = {"node": node, **itr.payload}
                self._save(thread_id, node, state)
                return state
            if update:
                state.update(update)
            edge = self.g.edges[node]
            nxt = edge(state) if callable(edge) else edge
            if nxt != END and nxt not in self.g.nodes:
                raise GraphError(f"router of {node!r} returned unknown node {nxt!r}")
            if self.on_transition:
                self.on_transition(node, nxt)
            self._save(thread_id, nxt, state)
            node = nxt
        raise GraphError(f"graph did not terminate within {max_steps} steps")
