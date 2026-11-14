"""Tool registries: three ways to decide what the model sees and what reaches the backend.

* `StaticRegistry`  - every tool, always exposed, no pre-validation.
* `ScopedRegistry`  - capability (domain) scoping + schema validation before execution.
* `LazyRegistry`    - only a `search_tools` meta-tool up front; schemas load on demand.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ..core.types import ToolCall, ToolResult, ToolSpec
from ..sim.world import WORLD_SPECS, World


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    fn: Callable[[ToolCall], ToolResult]


def world_tools(world: World, names: Iterable[str] = ("lookup", "compute", "write", "send")) -> list[Tool]:
    return [Tool(WORLD_SPECS[n], world.execute) for n in names]


_DISTRACTOR_AREAS = {
    "crm": ["get_contact", "update_contact", "list_deals", "create_deal", "log_activity", "merge_contacts", "search_accounts"],
    "calendar": ["list_events", "create_event", "cancel_event", "find_free_slot", "invite_attendee", "set_reminder", "move_event"],
    "billing": ["get_invoice", "create_invoice", "refund_payment", "list_subscriptions", "apply_coupon", "void_invoice", "export_ledger"],
    "files": ["read_file", "write_file", "list_directory", "move_file", "delete_file", "search_files", "stat_file"],
    "web": ["fetch_url", "search_web", "screenshot_page", "extract_links", "submit_form", "download_asset", "check_robots"],
}


def distractor_tools(n: int = 35) -> list[Tool]:
    """Plausible but irrelevant tools, used to study prompt bloat. Calling one is an error."""
    out: list[Tool] = []
    for area, names in _DISTRACTOR_AREAS.items():
        for name in names:
            full = f"{area}_{name}"
            spec = ToolSpec(
                full,
                f"{name.replace('_', ' ').capitalize()} in the {area} system. Requires a resource id and optional filters; returns a JSON record.",
                {"resource_id": "string", "filters": "any", "limit": "number"},
                "read" if name.split("_")[0] in ("get", "list", "search", "find", "read", "stat", "fetch", "check", "extract") else "write",
                True,
                area,
            )
            out.append(Tool(spec, lambda call: ToolResult(False, error_code="NOT_APPLICABLE", error="tool is unrelated to this task")))
    return out[:n]


def validate_args(spec: ToolSpec, args: dict[str, Any]) -> str:
    """Return an error description, or '' when `args` satisfy the spec."""
    missing = [k for k in spec.params if k not in args]
    extra = [k for k in args if k not in spec.params]
    if missing or extra:
        return f"missing={missing} unexpected={extra}"
    for k, t in spec.params.items():
        v = args[k]
        if t == "string" and not isinstance(v, str):
            return f"{k} must be a string"
        if t == "number" and (isinstance(v, bool) or not isinstance(v, (int, float))):
            return f"{k} must be a number"
        rule = spec.constraints.get(k, {})
        if "enum" in rule and v not in rule["enum"]:
            return f"{k} must be one of {rule['enum']}"
        if "pattern" in rule and not re.match(rule["pattern"], str(v)):
            return f"{k} does not match {rule['pattern']}"
    return ""


class StaticRegistry:
    name = "static"

    def __init__(self, tools: Iterable[Tool]):
        self._tools = {t.spec.name: t for t in tools}

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.tool)
        if tool is None:
            return ToolResult(False, error_code="UNKNOWN_TOOL", error=f"no such tool: {call.tool}")
        return tool.fn(call)


class ScopedRegistry:
    """Expose only tools in the granted domains; reject malformed calls before the backend sees them."""

    name = "scoped"

    def __init__(self, tools: Iterable[Tool], domains: Iterable[str] | None = None, validate: bool = True):
        self._all = {t.spec.name: t for t in tools}
        self._domains = set(domains) if domains is not None else None
        self._validate = validate
        self.rejected = 0

    def scope(self, domains: Iterable[str]) -> "ScopedRegistry":
        """A narrower view. Scopes can only shrink: the result is intersected with this one."""
        wanted = set(domains)
        if self._domains is not None:
            wanted &= self._domains
        return ScopedRegistry(self._all.values(), wanted, self._validate)

    def _visible(self) -> dict[str, Tool]:
        if self._domains is None:
            return self._all
        return {n: t for n, t in self._all.items() if t.spec.domain in self._domains}

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._visible().values()]

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self._visible().get(call.tool)
        if tool is None:
            self.rejected += 1
            return ToolResult(False, error_code="UNKNOWN_TOOL", error=f"tool not available in this scope: {call.tool}")
        if self._validate:
            problem = validate_args(tool.spec, call.args)
            if problem:
                self.rejected += 1
                return ToolResult(False, error_code="INVALID_ARGS", error=problem)
        return tool.fn(call)


class LazyRegistry:
    """Progressive disclosure: the model searches for tools, matching schemas are loaded into context."""

    name = "lazy"
    SEARCH = ToolSpec("search_tools", "Find tools by capability keyword and load their schemas.", {"query": "string"}, "read", True, "meta")

    def __init__(self, tools: Iterable[Tool], preload: Iterable[str] = (), top_k: int = 4):
        self._all = {t.spec.name: t for t in tools}
        self._loaded: list[str] = [n for n in preload if n in self._all]
        self._top_k = top_k
        self.searches = 0

    def specs(self) -> list[ToolSpec]:
        return [self.SEARCH] + [self._all[n].spec for n in self._loaded]

    def search(self, query: str) -> list[str]:
        q = query.lower()
        scored = []
        for name, t in self._all.items():
            score = 3 * (t.spec.domain == q) + 2 * (q in name.lower()) + (q in t.spec.description.lower())
            if score:
                scored.append((-score, name))
        return [name for _, name in sorted(scored)[: self._top_k]]

    def execute(self, call: ToolCall) -> ToolResult:
        if call.tool == "search_tools":
            self.searches += 1
            if not isinstance(call.args.get("query"), str):
                return ToolResult(False, error_code="INVALID_ARGS", error="query must be a string")
            hits = self.search(call.args["query"])
            for name in hits:
                if name not in self._loaded:
                    self._loaded.append(name)
            return ToolResult(True, hits)
        if call.tool not in self._loaded:
            return ToolResult(False, error_code="UNKNOWN_TOOL", error=f"tool not loaded: {call.tool}; use search_tools first")
        return self._all[call.tool].fn(call)
