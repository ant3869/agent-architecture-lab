"""Mount the tools of any MCP server (stdio transport) as an agentlab `ToolExecutor`.

Requires the optional dependency:  pip install "agentlab[mcp]"

The official MCP client is async and its session must be opened and closed by the same
task. This adapter owns one background event loop with one long-lived task that holds
the session, and exposes a small synchronous surface to the (synchronous) loops.
"""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Awaitable, Callable

from ..core.types import ToolCall, ToolResult, ToolSpec

_JSON_TYPES = {"string": "string", "number": "number", "integer": "number"}


class MCPConnectionError(RuntimeError):
    pass


def spec_from_mcp(tool: Any) -> ToolSpec:
    """Translate an MCP tool definition into a ToolSpec, including its risk tier.

    Risk tier comes from MCP tool annotations: readOnlyHint -> read; otherwise
    openWorldHint -> external; otherwise write. Annotations are hints from the server:
    treat them as untrusted unless you trust the server.
    """
    schema = tool.inputSchema if hasattr(tool, "inputSchema") else tool.input_schema
    props: dict[str, dict[str, Any]] = schema.get("properties", {})
    params = {k: _JSON_TYPES.get(v.get("type", ""), "any") for k, v in props.items() if k != "idempotency_key"}
    constraints = {k: {c: v[c] for c in ("enum", "pattern") if c in v} for k, v in props.items() if "enum" in v or "pattern" in v}
    ann = tool.annotations
    hint = lambda name: getattr(ann, name, None) if ann is not None else None
    read_only = bool(hint("readOnlyHint") if hint("readOnlyHint") is not None else hint("read_only_hint"))
    open_world = hint("openWorldHint") if hint("openWorldHint") is not None else hint("open_world_hint")
    idem = hint("idempotentHint") if hint("idempotentHint") is not None else hint("idempotent_hint")
    effect = "read" if read_only else ("external" if open_world else "write")
    meta = getattr(tool, "meta", None) or {}
    return ToolSpec(tool.name, tool.description or "", params, effect, bool(read_only or idem), str(meta.get("agentlab/domain", "general")), constraints)


class MCPToolset:
    """A ToolExecutor backed by an MCP server process.

        with MCPToolset("node", ["dist/server.js", "seed.json"], hidden={"dump_state"}) as tools:
            ReActLoop(Runtime(model, tools)).run(goal)
    """

    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None, hidden: set[str] | None = None, timeout_s: float = 20.0):
        try:
            import mcp  # noqa: F401
        except ImportError as e:  # pragma: no cover - exercised only without the extra
            raise MCPConnectionError('the MCP integration needs the optional dependency: pip install "agentlab[mcp]"') from e
        self._command, self._args, self._env = command, args, env
        self._hidden = hidden or set()
        self._timeout = timeout_s
        self._loop = asyncio.new_event_loop()
        self._queue: asyncio.Queue[tuple[Callable[[Any], Awaitable[Any]], Future] | None] | None = None
        self._ready: Future = Future()
        self._specs: dict[str, ToolSpec] = {}
        self._accepts_idem: set[str] = set()
        self._thread = threading.Thread(target=self._run_loop, name="mcp-toolset", daemon=True)
        self._thread.start()
        try:
            self._ready.result(timeout=timeout_s)
        except Exception as e:
            self.close()
            raise MCPConnectionError(f"could not start MCP server {command} {' '.join(args)}: {e}") from e

    # -- background task that owns the session -----------------------------------
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            if not self._ready.done():
                self._ready.set_exception(e)
        finally:
            self._loop.close()

    async def _main(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._queue = asyncio.Queue()
        params = StdioServerParameters(command=self._command, args=self._args, env=self._env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                for tool in listed.tools:
                    self._specs[tool.name] = spec_from_mcp(tool)
                    schema = tool.inputSchema if hasattr(tool, "inputSchema") else tool.input_schema
                    if "idempotency_key" in schema.get("properties", {}):
                        self._accepts_idem.add(tool.name)
                self._ready.set_result(True)
                while True:
                    item = await self._queue.get()
                    if item is None:
                        return
                    fn, fut = item
                    try:
                        fut.set_result(await fn(session))
                    except Exception as e:  # surfaced to the caller as a ToolResult
                        fut.set_exception(e)

    def _submit(self, fn: Callable[[Any], Awaitable[Any]]) -> Any:
        if self._queue is None or not self._thread.is_alive():
            raise MCPConnectionError("MCP session is closed")
        fut: Future = Future()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (fn, fut))
        return fut.result(timeout=self._timeout)

    # -- ToolExecutor -------------------------------------------------------------
    def specs(self) -> list[ToolSpec]:
        return [s for name, s in self._specs.items() if name not in self._hidden]

    def call_raw(self, name: str, arguments: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Call any server tool (including hidden ones). Returns (is_error, structured_content)."""
        result = self._submit(lambda s: s.call_tool(name, arguments))
        is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
        structured = getattr(result, "structuredContent", None)
        if structured is None:
            structured = getattr(result, "structured_content", None)
        return is_error, dict(structured or {})

    def execute(self, call: ToolCall) -> ToolResult:
        if call.tool not in self._specs or call.tool in self._hidden:
            return ToolResult(False, error_code="UNKNOWN_TOOL", error=f"no such tool: {call.tool}")
        args = dict(call.args)
        if call.idem_key and call.tool in self._accepts_idem:
            args["idempotency_key"] = call.idem_key
        try:
            is_error, data = self.call_raw(call.tool, args)
        except MCPConnectionError:
            raise
        except TimeoutError:
            return ToolResult(False, error_code="TIMEOUT", error="MCP call timed out; outcome unknown", retryable=True)
        except Exception as e:  # protocol-level failure (e.g. schema rejection by the server SDK)
            return ToolResult(False, error_code="PROTOCOL_ERROR", error=str(e))
        if is_error:
            return ToolResult(False, error_code=str(data.get("code", "TOOL_ERROR")), error=str(data.get("message", "")), info=dict(data.get("info", {})))
        return ToolResult(True, data.get("output"), deduped=bool(data.get("deduped", False)))

    # -- lifecycle ----------------------------------------------------------------
    def close(self) -> None:
        if self._queue is not None and self._thread.is_alive():
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
        self._thread.join(timeout=self._timeout)

    def __enter__(self) -> "MCPToolset":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
