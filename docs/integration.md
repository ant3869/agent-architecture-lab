# Integration guide

How to take a pattern out of this repository and into a real system. Each pattern page also has its own integration snippet.

## 1. The two protocols

Everything is written against two interfaces in [`core/types.py`](../src/agentlab/core/types.py):

```python
class Model(Protocol):
    def complete(self, req: ModelRequest) -> ModelResponse: ...

class ToolExecutor(Protocol):
    def specs(self) -> list[ToolSpec]: ...          # tools currently exposed to the model
    def execute(self, call: ToolCall) -> ToolResult: ...
```

To use a pattern you supply a `Model` and a `ToolExecutor` and pass them to a `Runtime`. Nothing else in the library needs to change.

### What the model must be able to answer

`ModelRequest.mode` says what is being asked. A loop only uses the modes listed for it.

| Mode | Used by | Expected in `ModelResponse` |
|---|---|---|
| `act` | ReAct, supervisor workers, handoff peers | `call` (one `ToolCall`) or `final=True` |
| `finalize` | Plan-and-Execute, verified graph, supervisor | `final=True`, answer in `text` |
| `plan`, `replan` | Plan-and-Execute, verified graph | `plan`: list of `ToolCall`; an argument may be `{"$ref": "<step_id>"}` |
| `verify` | Verified graph | `data = {"invalid": [step_id, ...], "proposed_ok": bool}`; request `params` carry `audit` and `proposed` |
| `decompose` | Supervisor | `data = {"subtasks": [{"id", "domain", "steps", "needs"}]}` |
| `summarize` | Compaction | `data = {"facts", "done", "moved", "attempts"}` |

`ToolCall.step_id` is the model's label for which sub-goal a call serves. With a real model use the provider's tool-call id.

## 2. Running on a real model

[`agentlab.integrations.anthropic_model.AnthropicModel`](../src/agentlab/integrations/anthropic_model.py) implements `act` and `finalize` on the Anthropic Messages API, which is enough for `ReActLoop` and every wrapper around it.

1. Install the extra.

```bash
pip install -e ".[anthropic]"
```

2. Provide credentials the Anthropic SDK can resolve (for example the `ANTHROPIC_API_KEY` environment variable).

3. Build the runtime with your own tools.

```python
from agentlab.core.runtime import Runtime
from agentlab.core.types import Message
from agentlab.integrations.anthropic_model import AnthropicModel
from agentlab.loops.react import ReActLoop

rt = Runtime(AnthropicModel(), my_tools)          # my_tools: any ToolExecutor
result = ReActLoop(rt, max_iters=40).run(Message("user", "Reconcile yesterday's orders and notify ops."))
```

Adapter behaviour worth knowing:

- It requests one tool call per turn, replays each assistant turn exactly as the API returned it, and maps tool errors to `is_error` tool results so the model can correct itself.
- It enables server-side refusal fallback by default (`refusal_fallback=True`, a beta feature); a refusal that survives becomes a final response with `data["blocked"]`.
- Token counts and cost come from the API's `usage`; prices are a constructor argument.
- It is covered by contract tests against a stub client ([`tests/test_anthropic_adapter.py`](../tests/test_anthropic_adapter.py)). **It has not been exercised against the live API in this repository.**

The structured modes (`plan`, `verify`, `decompose`, `summarize`) are not implemented for real models: they need task-specific prompts and output schemas. To add one, subclass the adapter, prompt for JSON matching the table above (structured outputs are the right tool), and parse it into `ModelResponse.plan` or `.data`. Any other provider is adapted the same way: implement `complete` for the modes your loop uses.

## 3. Bringing your own tools

**In-process functions.** Wrap each function in a `Tool(spec, fn)` and put them in a registry:

```python
from agentlab.core.types import ToolResult, ToolSpec
from agentlab.tools.registry import ScopedRegistry, Tool

def get_order(call):
    try:
        return ToolResult(True, orders.fetch(call.args["order_id"]))
    except KeyError:
        return ToolResult(False, error_code="NOT_FOUND", error="no such order")
    except TimeoutError:
        return ToolResult(False, error_code="TIMEOUT", error="order service timed out", retryable=True)

spec = ToolSpec("get_order", "Fetch an order by id.", {"order_id": "string"}, effect="read", idempotent=True, domain="orders")
tools = ScopedRegistry([Tool(spec, get_order)])
```

Three fields drive the middleware: `effect` (`read` / `write` / `external`) is the risk tier used by approval gates and the verified graph; `idempotent` decides whether runtime retries are allowed; `retryable` on a failed `ToolResult` separates infrastructure faults from caller errors. Set them truthfully.

**Any MCP server.** [`MCPToolset`](../src/agentlab/integrations/mcp_tools.py) mounts a stdio MCP server's tools as a `ToolExecutor`, mapping MCP tool annotations to risk tiers and passing idempotency keys through when the tool accepts an `idempotency_key` argument.

```python
from agentlab.integrations.mcp_tools import MCPToolset

with MCPToolset("node", ["integrations/mcp-tool-server/dist/server.js", "seed.json"]) as tools:
    ReActLoop(Runtime(model, tools)).run(goal)
```

The repository's own TypeScript server and the Python loops are tested against each other in [`tests/test_interop_mcp.py`](../tests/test_interop_mcp.py). Tool annotations come from the server; treat them as untrusted unless you trust the server.

## 4. Stacking middleware

Wrappers compose because each is itself a `ToolExecutor`. Order matters; outermost first:

```python
tools = registry                                             # what exists (Static / Scoped / Lazy / MCP)
tools = RetryingTools(tools, clock, RetryPolicy())           # absorb transient faults
tools = CircuitBreakerTools(tools, clock, fallbacks={...})   # stop calling a dead dependency
tools = IdempotentTools(tools, namespace=run_id)             # key side effects (must sit above retries)
tools = CapabilityTools(tools, secret, token, clock)         # authorization on arguments
tools = ApprovalTools(tools, ask=("external",))              # human decision for the risky tier
tools = session.tools(tools)                                 # journal: outermost, so recorded results skip everything below
```

Reasons for the order: authorization and approval must see every call the model makes, before any retry; the idempotency key must be attached before a retry layer decides whether a retry is safe; the journal must be outermost so that a replayed call touches nothing.

## 5. Mapping to frameworks

If you already use a framework, take the pattern, not the code.

| Pattern here | LangGraph | OpenAI Agents SDK | CrewAI | MS Agent Framework |
|---|---|---|---|---|
| ReAct loop | prebuilt ReAct agent | `Runner` loop | agent executor | chat agent |
| Plan-and-Execute | plan node + executor node | planner agent as tool | Flow with a planning step | workflow |
| Verified graph | `StateGraph` with a verify node before effect nodes | tool guardrails | Flow with a router | graph workflow |
| Supervisor-worker | supervisor graph | agents-as-tools | hierarchical process | orchestration workflow |
| Peer handoff | swarm graph | handoffs | (delegate tool) | handoff orchestration |
| Snapshot durability | checkpointer | sessions (history) | flow state | session state |
| Journal durability | run inside a durable-execution engine | same | same | same |
| Approval | `interrupt()` / `Command(resume=)` | tool approval | human input | tool approval |
| Tracing | LangSmith / OTel | built-in tracing | OTel integrations | OTel |

The "who decides the next step" row in [`research/frameworks.md`](../research/frameworks.md) tells you which of these a framework makes easy.

## 6. A checklist before production

1. Every non-idempotent tool accepts an idempotency key, and the runtime sends one.
2. Retries are bounded and only applied to retryable errors on idempotent or keyed calls.
3. Authorization is enforced outside the model and constrains arguments for any tool that takes a destination.
4. Runs are resumable (journal or checkpoints), and you have crashed one on purpose at a side-effect boundary.
5. Every model and tool call is traced from one place, and you can replay a recorded run.
6. Context is bounded by a policy you chose deliberately; you know what the agent does when it forgets.
7. Success is checked on the state of the world, not on the agent's report.
