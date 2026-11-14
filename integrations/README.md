# Integrations

Working connections between the reference implementations and things outside this repository.

| Integration | Where | Tested by |
|---|---|---|
| **MCP tools, across languages.** A TypeScript MCP server ([`mcp-tool-server/`](mcp-tool-server)) is driven by the unmodified Python loops through [`agentlab.integrations.mcp_tools.MCPToolset`](../src/agentlab/integrations/mcp_tools.py). | TypeScript + Python | [`tests/test_interop_mcp.py`](../tests/test_interop_mcp.py): discovery, typed errors, all three loops completing a task, idempotency keys across the protocol |
| **A real model.** [`agentlab.integrations.anthropic_model.AnthropicModel`](../src/agentlab/integrations/anthropic_model.py) implements the `Model` protocol on the Anthropic Messages API. | Python | [`tests/test_anthropic_adapter.py`](../tests/test_anthropic_adapter.py): contract tests against a stub client. Not exercised against the live API. |

Usage for both is in [`docs/integration.md`](../docs/integration.md).

## Running the cross-language test

1. Install the Python extra.

```bash
pip install -e ".[mcp]"
```

2. Build the server.

```bash
cd integrations/mcp-tool-server && npm install && npm run build
```

3. Run the interop tests from the repository root.

```bash
pytest tests/test_interop_mcp.py
```

Without the extra or the built server these tests are skipped, not failed.
