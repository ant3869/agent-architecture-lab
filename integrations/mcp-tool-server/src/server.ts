/**
 * Inventory tool server over MCP (stdio transport).
 *
 * An independent TypeScript implementation of the same tool contract the Python
 * simulator exposes (lookup / compute / write / send). The Python side mounts these
 * tools into an agentlab registry and drives them with an unmodified agent loop.
 *
 * Usage: node dist/server.js <seed.json>
 *   seed.json: { "kv": {key: number}, "moved": {oldKey: newKey}, "recipients": [string] }
 *
 * Conventions that matter for agents:
 *  - Failures are returned as tool results with isError=true and a machine-readable
 *    code, never as protocol errors, so the model can read them and self-correct.
 *  - `send` accepts an idempotency_key and applies each key at most once.
 *  - Tool annotations declare read-only / idempotent / open-world behaviour so a
 *    client can gate risky calls without parsing descriptions.
 */
import { readFileSync } from "node:fs";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

interface Seed {
  kv: Record<string, number>;
  moved: Record<string, string>;
  recipients: string[];
}

class ToolFailure extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly info: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const KEY_PATTERN = /^[a-z0-9:._-]+$/;
const OPS: Record<string, (a: number, b: number) => number> = {
  add: (a, b) => a + b,
  sub: (a, b) => a - b,
  mul: (a, b) => a * b,
};

function loadSeed(path: string | undefined): Seed {
  if (!path) {
    return { kv: {}, moved: {}, recipients: ["ops", "audit"] };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(path, "utf8"));
  } catch (err) {
    throw new Error(`cannot read seed file ${path}: ${(err as Error).message}`);
  }
  const shape = z.object({
    kv: z.record(z.string(), z.number()),
    moved: z.record(z.string(), z.string()).default({}),
    recipients: z.array(z.string()).default(["ops", "audit"]),
  });
  return shape.parse(parsed);
}

const seed = loadSeed(process.argv[2]);
const kv = new Map<string, unknown>(Object.entries(seed.kv));
const writes: Array<[string, unknown]> = [];
const outbox: Array<[string, unknown]> = [];
const idempotencyRecords = new Map<string, CallToolResult>();

function ok(output: unknown): CallToolResult {
  return {
    content: [{ type: "text", text: JSON.stringify(output) }],
    structuredContent: { output },
  };
}

function fail(code: string, message: string, info: Record<string, unknown> = {}): CallToolResult {
  return {
    isError: true,
    content: [{ type: "text", text: `ERROR ${code}: ${message}` }],
    structuredContent: { code, message, info },
  };
}

/** Run a handler and convert every failure into an in-band tool error. */
function guarded(fn: () => unknown): CallToolResult {
  try {
    return ok(fn());
  } catch (err) {
    if (err instanceof ToolFailure) {
      return fail(err.code, err.message, err.info);
    }
    return fail("INTERNAL", err instanceof Error ? err.message : String(err));
  }
}

const server = new McpServer({ name: "agentlab-inventory", version: "0.1.0" });

server.registerTool(
  "lookup",
  {
    title: "Look up a value",
    description: "Read the value stored under a key in the inventory store.",
    inputSchema: { key: z.string() },
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
    _meta: { "agentlab/domain": "data" },
  },
  async ({ key }) =>
    guarded(() => {
      const movedTo = seed.moved[key];
      if (movedTo !== undefined) {
        throw new ToolFailure("MOVED", `${key} moved to ${movedTo}`, { moved_to: movedTo });
      }
      if (!kv.has(key)) {
        throw new ToolFailure("NOT_FOUND", `no such key: ${key}`);
      }
      return kv.get(key);
    }),
);

server.registerTool(
  "compute",
  {
    title: "Compute",
    description: "Apply op (add, sub, mul) to two numbers.",
    inputSchema: { op: z.string(), a: z.number(), b: z.number() },
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
    _meta: { "agentlab/domain": "math" },
  },
  async ({ op, a, b }) =>
    guarded(() => {
      const fn = OPS[op];
      if (!fn) {
        throw new ToolFailure("INVALID_OP", `unsupported op: ${op}`);
      }
      return fn(a, b);
    }),
);

server.registerTool(
  "write",
  {
    title: "Write a report value",
    description: "Persist a value under a report key.",
    inputSchema: { key: z.string(), value: z.unknown() },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    _meta: { "agentlab/domain": "ops" },
  },
  async ({ key, value }) =>
    guarded(() => {
      if (!KEY_PATTERN.test(key)) {
        throw new ToolFailure("INVALID_KEY", `malformed key: ${key}`);
      }
      kv.set(key, value);
      writes.push([key, value]);
      return "written";
    }),
);

server.registerTool(
  "send",
  {
    title: "Send a notification",
    description: "Send a notification to a recipient. Not idempotent unless idempotency_key is supplied.",
    inputSchema: { to: z.string(), body: z.unknown(), idempotency_key: z.string().optional() },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
    _meta: { "agentlab/domain": "ops" },
  },
  async ({ to, body, idempotency_key }) => {
    if (idempotency_key !== undefined) {
      const previous = idempotencyRecords.get(idempotency_key);
      if (previous) {
        return { ...previous, structuredContent: { ...previous.structuredContent, deduped: true } };
      }
    }
    const result = guarded(() => {
      if (!seed.recipients.includes(to)) {
        throw new ToolFailure("UNKNOWN_RECIPIENT", `no such recipient: ${to}`);
      }
      outbox.push([to, body]);
      return "sent";
    });
    if (idempotency_key !== undefined && !result.isError) {
      idempotencyRecords.set(idempotency_key, result);
    }
    return result;
  },
);

server.registerTool(
  "dump_state",
  {
    title: "Dump effects",
    description: "Return every write and notification applied so far. For test harnesses, not for agents.",
    inputSchema: {},
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
    _meta: { "agentlab/domain": "admin" },
  },
  async () => ok({ writes, outbox }),
);

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stdout carries the protocol; diagnostics go to stderr only.
  process.stderr.write(`agentlab-inventory ready (${kv.size} keys)\n`);
}

main().catch((err) => {
  process.stderr.write(`fatal: ${err instanceof Error ? err.stack : String(err)}\n`);
  process.exit(1);
});
