# MCP tool server (TypeScript)

An inventory service exposed over the Model Context Protocol on stdio, written with the official TypeScript SDK. It implements the same tool contract as the Python simulator (`lookup`, `compute`, `write`, `send`) independently, so the Python agent loops can be tested against a real out-of-process, other-language tool backend.

```bash
npm install && npm run build
```

```bash
node dist/server.js seed.json
```

`seed.json` is `{ "kv": {key: number}, "moved": {oldKey: newKey}, "recipients": [string] }`.

Design points that matter to an agent:

- **Errors are tool results.** Every failure is returned with `isError: true` and `structuredContent: { code, message, info }`, never as a protocol error, so a model can read it and correct the call.
- **Idempotency.** `send` accepts an optional `idempotency_key` and applies each key at most once.
- **Annotations.** Each tool declares `readOnlyHint`, `idempotentHint` and `openWorldHint`; the Python bridge maps them to risk tiers.
- **`dump_state`** returns the effects applied so far. It exists for test harnesses and is hidden from the model by the bridge.
