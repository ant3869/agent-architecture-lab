import { useMemo, useState } from "react";
import { Card, Load, Pill, SectionTitle, Stat, StatusBadge } from "../components/ui";
import { useTrace } from "../lib/data";
import { compact, ms } from "../lib/format";
import { href, navigate } from "../lib/router";
import type { Catalog, TimelineRow, Trace, TraceEvent } from "../types";

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => (typeof v === "object" && v !== null ? (v as Obj) : {});
const str = (v: unknown): string => (typeof v === "string" ? v : v === undefined || v === null ? "" : JSON.stringify(v));
const num = (v: unknown): number => (typeof v === "number" ? v : 0);

const KINDS: { id: string; label: string; dot: string }[] = [
  { id: "model_call", label: "Model calls", dot: "bg-series-1" },
  { id: "tool_result", label: "Tool calls", dot: "bg-series-3" },
  { id: "message", label: "Agent messages", dot: "bg-series-4" },
  { id: "transition", label: "State transitions", dot: "bg-series-2" },
  { id: "note", label: "Runtime notes", dot: "bg-ink-3" },
];

interface Line {
  label: string;
  text: string;
  flags: string[];
  failed: boolean;
}

function describe(e: TraceEvent): Line {
  const d = e.data;
  if (e.kind === "model_call") {
    const r = obj(d.response);
    const flags = [`${num(r.prompt_tokens)} in / ${num(r.completion_tokens)} out`];
    if (r.replayed) flags.push("replayed from journal");
    const first = str(r.text).split("\n").filter(Boolean);
    return { label: `model · ${str(d.mode)}`, text: first[first.length - 1] ?? "", flags, failed: false };
  }
  if (e.kind === "tool_result") {
    const c = obj(d.call);
    const r = obj(d.result);
    const flags: string[] = [];
    if (num(r.attempts) > 1) flags.push(`${num(r.attempts)} attempts`);
    if (r.deduped) flags.push("deduplicated by idempotency key");
    if (r.replayed) flags.push("replayed from journal");
    const outcome = r.ok ? `→ ${str(r.output)}` : `→ ${str(r.error_code)}: ${str(r.error)}`;
    return { label: `tool · ${str(c.tool)}`, text: `${str(c.tool)}(${JSON.stringify(c.args)}) ${outcome}`, flags, failed: !r.ok };
  }
  if (e.kind === "message") return { label: `message · ${str(d.msg_kind)}`, text: `${e.agent} → ${str(d.to)} (${num(d.tokens)} tokens): ${str(d.text).slice(0, 140)}`, flags: [], failed: false };
  if (e.kind === "transition") return { label: "transition", text: `${str(d.src)} → ${str(d.dst)}`, flags: [], failed: false };
  if (e.kind === "note") return { label: "note", text: str(d.text), flags: [], failed: /crash/i.test(str(d.text)) };
  return { label: e.kind, text: str(d.name ?? d.status ?? ""), flags: [], failed: false };
}

function ContextStrip({ events }: { events: TraceEvent[] }) {
  const calls = events.filter((e) => e.kind === "model_call" && !obj(e.data.response).replayed);
  const [hover, setHover] = useState<number | null>(null);
  if (calls.length < 2) return null;
  const values = calls.map((e) => num(obj(e.data.response).prompt_tokens));
  const max = Math.max(...values) || 1;
  const h = hover !== null ? calls[hover] : undefined;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs text-ink-3">
        <span>Prompt tokens per model call, in order</span>
        <span className="tabular-nums">{h ? `call ${hover! + 1} · ${h.agent} · ${str(h.data.mode)} · ${values[hover!]} tokens` : `peak ${compact(max)}`}</span>
      </div>
      <div className="flex h-20 items-end gap-[2px] border-b border-line" role="img" aria-label={`Prompt tokens for each of ${calls.length} model calls; peak ${max}`} onMouseLeave={() => setHover(null)}>
        {values.map((v, i) => (
          <div key={i} className="flex h-full min-w-0 flex-1 items-end" style={{ maxWidth: 24 }} onMouseEnter={() => setHover(i)}>
            <div className={`w-full rounded-t-[3px] ${hover === i ? "bg-accent-soft" : "bg-series-1"}`} style={{ height: `${Math.max(2, (v / max) * 100)}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function Gantt({ rows }: { rows: TimelineRow[] }) {
  const workers = [...new Set(rows.map((r) => r.worker))];
  const end = Math.max(...rows.map((r) => r.end), 1);
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-4 text-xs text-ink-2">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-4 rounded-sm bg-series-1" /> completed subtask
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-4 rounded-sm bg-critical" /> ✕ worker crashed
        </span>
        <span className="ml-auto tabular-nums text-ink-3">0 – {ms(end)} after decomposition</span>
      </div>
      <div className="space-y-[2px]">
        {workers.map((w) => (
          <div key={w} className="grid grid-cols-[4.5rem_1fr] items-center gap-3">
            <span className="text-right font-mono text-xs text-ink-2">{w}</span>
            <div className="relative h-6 rounded bg-surface-2">
              {rows
                .filter((r) => r.worker === w)
                .map((r) => (
                  <div
                    key={`${r.subtask}-${r.start}`}
                    title={`${r.subtask} on ${w}: ${ms(r.start)} – ${ms(r.end)} (${r.state})`}
                    className={`absolute inset-y-[3px] flex items-center overflow-hidden rounded-[3px] px-1 text-[10px] text-white ${r.state === "crashed" ? "bg-critical" : "bg-series-1"}`}
                    style={{ left: `${(r.start / end) * 100}%`, width: `calc(${((r.end - r.start) / end) * 100}% - 2px)` }}
                  >
                    <span className="truncate">
                      {r.state === "crashed" ? "✕ " : ""}
                      {r.subtask}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Viewer({ trace }: { trace: Trace }) {
  const [kinds, setKinds] = useState<Set<string>>(() => new Set(KINDS.map((k) => k.id)));
  const [agent, setAgent] = useState("all");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const agents = useMemo(() => [...new Set(trace.events.map((e) => e.agent).filter(Boolean))], [trace]);
  const rows = useMemo(
    () =>
      trace.events
        .filter((e) => kinds.has(e.kind) && (agent === "all" || e.agent === agent))
        .map((e) => ({ e, line: describe(e) }))
        .filter((r) => !errorsOnly || r.line.failed),
    [trace, kinds, agent, errorsOnly],
  );
  const s = trace.summary;
  const toggle = (id: string) =>
    setKinds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="space-y-5">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-semibold text-ink">{trace.title}</h2>
          <StatusBadge kind={s.outcome} />
        </div>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-2">{trace.description}</p>
        <a className="mt-1 inline-block text-sm text-accent-soft underline" href={href(["patterns", trace.pattern], { s: trace.solution })}>
          Pattern and code for this run
        </a>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Task steps" value={s.steps} />
        <Stat label="Model calls" value={s.model_calls} />
        <Stat label="Tool calls" value={s.tool_calls} sub={`${s.backend_calls} reached the backend`} />
        <Stat label="Tokens" value={compact(s.tokens)} />
        <Stat label="Peak context" value={compact(s.peak_context)} sub="tokens in one prompt" />
        <Stat label="Simulated time" value={ms(s.makespan_ms ?? s.sim_ms)} sub={s.makespan_ms ? `${ms(s.sim_ms)} of total work` : undefined} />
      </div>

      <Card className="space-y-5 p-5">
        <ContextStrip events={trace.events} />
        {trace.timeline ? (
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Worker schedule</h3>
            <Gantt rows={trace.timeline} />
          </div>
        ) : null}
        <details>
          <summary className="cursor-pointer text-sm text-ink-2 hover:text-ink">Task given to the agent</summary>
          <p className="mt-2 font-mono text-xs leading-relaxed text-ink-3">{trace.goal}</p>
        </details>
      </Card>

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-4">
          {KINDS.filter((k) => trace.events.some((e) => e.kind === k.id)).map((k) => (
            <Pill key={k.id} active={kinds.has(k.id)} onClick={() => toggle(k.id)}>
              <span aria-hidden className={`mr-1.5 inline-block h-2 w-2 rounded-full ${k.dot}`} />
              {k.label}
            </Pill>
          ))}
          <Pill active={errorsOnly} onClick={() => setErrorsOnly((v) => !v)}>
            Failures only
          </Pill>
          {agents.length > 1 ? (
            <label className="ml-auto flex items-center gap-2 text-xs text-ink-3">
              Agent
              <select value={agent} onChange={(e) => setAgent(e.target.value)} className="rounded-md border border-line bg-surface-2 px-2 py-1 text-sm text-ink">
                <option value="all">all</option>
                {agents.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>
        {rows.length === 0 ? (
          <p className="p-6 text-sm text-ink-2">No events match these filters. Turn a filter back on to see the run.</p>
        ) : (
          <ol className="divide-y divide-line/70" aria-label="Events">
            {rows.map(({ e, line }) => {
              const k = KINDS.find((x) => x.id === e.kind);
              const expanded = open === e.seq;
              return (
                <li key={e.seq}>
                  <button type="button" aria-expanded={expanded} onClick={() => setOpen(expanded ? null : e.seq)} className="grid w-full grid-cols-[3.75rem_1fr] items-baseline gap-x-3 gap-y-0.5 px-4 py-2 text-left hover:bg-surface-2 md:grid-cols-[4.5rem_6.5rem_9.5rem_1fr]">
                    <span className="font-mono text-xs tabular-nums text-ink-3">{ms(e.t_ms)}</span>
                    <span className="hidden truncate font-mono text-xs text-ink-2 md:block">{e.agent || "—"}</span>
                    <span className="flex min-w-0 items-center gap-2 text-xs text-ink-2">
                      <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${k?.dot ?? "bg-ink-3"}`} />
                      <span className="truncate">
                        <span className="md:hidden">{e.agent ? `${e.agent} · ` : ""}</span>
                        {line.label}
                      </span>
                    </span>
                    <span className="col-span-2 min-w-0 md:col-span-1">
                      <span className={`block truncate font-mono text-xs ${line.failed ? "text-ink" : "text-ink-2"}`}>
                        {line.failed ? (
                          <span className="mr-1.5 text-critical" aria-label="failed">
                            ✕
                          </span>
                        ) : null}
                        {line.text}
                      </span>
                      {line.flags.length > 0 ? <span className="mt-0.5 block text-[11px] text-ink-3">{line.flags.join(" · ")}</span> : null}
                    </span>
                  </button>
                  {expanded ? <pre className="max-h-96 overflow-auto border-t border-line bg-surface-0 px-4 py-3 font-mono text-xs leading-relaxed text-ink-2">{JSON.stringify(e.data, null, 2)}</pre> : null}
                </li>
              );
            })}
          </ol>
        )}
        <p className="border-t border-line px-4 py-2 text-xs text-ink-3">
          {rows.length} of {trace.events.length} events shown · select a row to see its full payload
        </p>
      </Card>
    </div>
  );
}

export function TracesView({ catalog, id }: { catalog: Catalog; id?: string }) {
  const current = catalog.traces.find((t) => t.id === id) ?? catalog.traces[0];
  const trace = useTrace(current?.id ?? null);
  if (!current) return <p className="text-sm text-ink-2">No traces were recorded. Run “python scripts/build_catalog.py”.</p>;
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Recorded execution traces</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-2">Real runs of the reference implementations, event by event. Each one can be replayed exactly from its recording.</p>
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[18rem_1fr]">
        <nav aria-label="Traces">
          <SectionTitle>Runs</SectionTitle>
          <ul className="space-y-1.5">
            {catalog.traces.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  aria-current={t.id === current.id ? "true" : undefined}
                  onClick={() => navigate(["traces", t.id])}
                  className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${t.id === current.id ? "border-accent bg-accent/10" : "border-line bg-surface-1 hover:border-ink-3"}`}
                >
                  <span className="block text-sm leading-snug text-ink">{t.title}</span>
                  <span className="mt-1 flex items-center gap-1.5 text-xs text-ink-3">
                    <span aria-hidden className={t.summary.outcome === "ok" ? "text-good" : "text-critical"}>
                      {t.summary.outcome === "ok" ? "✓" : "✕"}
                    </span>
                    {t.summary.outcome === "ok" ? "goal met" : t.summary.outcome.replace("_", " ")} · {t.events} events
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="min-w-0">
          <Load value={trace}>{(t) => <Viewer key={t.id} trace={t} />}</Load>
        </div>
      </div>
    </div>
  );
}
