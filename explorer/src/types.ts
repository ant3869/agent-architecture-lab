export interface Solution {
  id: string;
  name: string;
  status: "implemented" | "documented";
  summary: string;
  diagram?: string;
  implementation?: string;
  example?: string;
  tests?: string;
  result_arch?: string[];
  advantages: string[];
  limitations: string[];
  performance?: string;
  complexity?: string;
  reliability?: string;
  security?: string;
  use_when: string[];
  avoid_when: string[];
  integration?: string;
  frameworks: string;
}

export interface Pattern {
  id: string;
  order: number;
  title: string;
  tagline: string;
  problem: string;
  applications: string[];
  decision: string;
  experiment: string;
  research: string[];
  solutions: Solution[];
}

export interface Source {
  key: string;
  kind: string;
  title: string;
  authors: string;
  year: number;
  url: string;
  verified: "content" | "reachable" | "unverified";
  note: string;
  arxiv?: string;
}

export interface GuideEntry {
  problem: string;
  pattern: string;
  solution: string;
  recommendation: string;
  evidence: string;
}

export interface TraceSummary {
  status: string;
  outcome: string;
  steps: number;
  model_calls: number;
  tool_calls: number;
  backend_calls: number;
  tokens: number;
  peak_context: number;
  sim_ms: number;
  makespan_ms?: number;
}

export interface TraceIndexEntry {
  id: string;
  title: string;
  pattern: string;
  solution: string;
  description: string;
  goal: string;
  summary: TraceSummary;
  events: number;
}

export interface TraceEvent {
  seq: number;
  t_ms: number;
  kind: string;
  agent: string;
  span: string;
  data: Record<string, unknown>;
}

export interface TimelineRow {
  subtask: string;
  worker: string;
  start: number;
  end: number;
  state: string;
}

export interface Trace extends Omit<TraceIndexEntry, "events"> {
  events: TraceEvent[];
  timeline?: TimelineRow[];
}

export interface Catalog {
  patterns: Pattern[];
  guide: GuideEntry[];
  code: Record<string, string>;
  sources: Source[];
  manifest: { n: number; digest: string; experiments: string[] };
  verification: { checked_on: string; total: number; ok: number; failed: string[] } | null;
  traces: TraceIndexEntry[];
}

export interface Column {
  key: string;
  label: string;
}

export type Row = Record<string, unknown> & { arch: string; scenario: string };

export interface Experiment {
  id: string;
  title: string;
  question: string;
  conditions: Record<string, unknown>;
  columns: Column[];
  group_by: string[];
  rows: Row[];
  findings: string[];
  limitations: string[];
}

export interface Results {
  experiments: Record<string, Experiment>;
  perf: { note: string; python: string; platform: string; rows: { arch: string; wall_ms_per_run: number; peak_alloc_kb: number }[] } | null;
}
