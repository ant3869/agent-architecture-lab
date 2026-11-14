import { ResultsPanel } from "../components/ResultsPanel";
import { Card, Pill, SectionTitle } from "../components/ui";
import { href, navigate } from "../lib/router";
import type { Catalog, Results } from "../types";

function renderCondition(v: unknown): string {
  return typeof v === "object" && v !== null ? JSON.stringify(v) : String(v);
}

export function ResultsView({ catalog, results, id }: { catalog: Catalog; results: Results; id?: string }) {
  const ids = catalog.manifest.experiments.filter((e) => e in results.experiments);
  const exp = results.experiments[id ?? ""] ?? results.experiments[ids[0] ?? ""];
  if (!exp) return <p className="text-sm text-ink-2">No results found. Run “python -m experiments.run_all”.</p>;
  const patterns = catalog.patterns.filter((p) => p.experiment === exp.id);
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Evaluation results</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-2">
          Every number is reproduced bit-for-bit by <code className="font-mono text-ink">python -m experiments.run_all</code> (n = {catalog.manifest.n}, digest <code className="font-mono text-ink">{catalog.manifest.digest.slice(0, 16)}</code>). Findings are measurements; recommendations live in the Guide.
        </p>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Experiment">
        {ids.map((e) => (
          <Pill key={e} active={e === exp.id} onClick={() => navigate(["results", e])}>
            {results.experiments[e]?.title ?? e}
          </Pill>
        ))}
      </div>

      <Card className="p-5">
        <h2 className="text-xl font-semibold text-ink">{exp.title}</h2>
        <p className="mt-1 text-sm text-ink-2">{exp.question}</p>
        {patterns.length > 0 ? (
          <p className="mt-2 text-sm text-ink-3">
            Pattern:{" "}
            {patterns.map((p) => (
              <a key={p.id} className="text-accent-soft underline" href={href(["patterns", p.id])}>
                {p.title}
              </a>
            ))}
          </p>
        ) : null}
        <div className="mt-5">
          <ResultsPanel key={exp.id} exp={exp} />
        </div>
      </Card>

      <Card className="p-5">
        <SectionTitle>Test conditions</SectionTitle>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm md:grid-cols-[14rem_1fr]">
          {Object.entries(exp.conditions).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-mono text-xs text-ink-3">{k}</dt>
              <dd className="min-w-0 font-mono text-xs text-ink-2 [overflow-wrap:anywhere]">{renderCondition(v)}</dd>
            </div>
          ))}
        </dl>
      </Card>

      {results.perf ? (
        <Card className="p-5">
          <SectionTitle hint="not part of the reproducible digest">Harness overhead on the machine that generated this site</SectionTitle>
          <p className="mb-3 text-sm text-ink-2">{results.perf.note}</p>
          <div className="overflow-x-auto">
            <table className="w-full max-w-xl text-left text-sm">
              <thead className="text-xs text-ink-3">
                <tr>
                  <th className="py-1.5 font-medium">Architecture</th>
                  <th className="py-1.5 text-right font-medium">Wall time per run (ms)</th>
                  <th className="py-1.5 text-right font-medium">Peak allocation (KB)</th>
                </tr>
              </thead>
              <tbody>
                {results.perf.rows.map((r) => (
                  <tr key={r.arch} className="border-t border-line">
                    <td className="py-1.5 text-ink">{r.arch}</td>
                    <td className="py-1.5 text-right tabular-nums text-ink-2">{r.wall_ms_per_run.toFixed(2)}</td>
                    <td className="py-1.5 text-right tabular-nums text-ink-2">{r.peak_alloc_kb.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-ink-3">
            Python {results.perf.python} on {results.perf.platform}
          </p>
        </Card>
      ) : null}
    </div>
  );
}
