import type { Row } from "../types";

const PERCENT_KEYS = new Set(["success_rate", "exfil_mean", "replay_identical"]);

export function formatValue(key: string, v: unknown): string {
  if (typeof v !== "number") return v === undefined || v === null ? "" : String(v);
  if (PERCENT_KEYS.has(key)) return `${(v * 100).toFixed(key === "success_rate" ? 1 : 0)}%`;
  if (Number.isInteger(v)) return v.toLocaleString("en-US");
  if (Math.abs(v) >= 100) return Math.round(v).toLocaleString("en-US");
  return v.toFixed(2);
}

export function compact(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 10_000) return `${(v / 1000).toFixed(0)}k`;
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(1)}k`;
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(Math.abs(v) < 10 ? 2 : 1);
}

export function isPercentKey(key: string): boolean {
  return PERCENT_KEYS.has(key);
}

export function numericKeys(rows: Row[], keys: string[]): string[] {
  return keys.filter((k) => rows.some((r) => typeof r[k] === "number"));
}

export function ms(v: number): string {
  return v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${v}ms`;
}
