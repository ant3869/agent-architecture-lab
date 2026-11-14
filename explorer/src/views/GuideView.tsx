import { useMemo, useState } from "react";
import { Card, Inline } from "../components/ui";
import { href } from "../lib/router";
import type { Catalog } from "../types";

export function GuideView({ catalog }: { catalog: Catalog }) {
  const [q, setQ] = useState("");
  const entries = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return catalog.guide;
    return catalog.guide.filter((e) => [e.problem, e.recommendation, e.evidence, e.pattern, e.solution].some((t) => t.toLowerCase().includes(needle)));
  }, [catalog.guide, q]);
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Find guidance for your problem</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-2">
          Each entry separates the <span className="text-ink">recommendation</span> (advice) from what was <span className="text-ink">measured here</span> (a result from this repository's simulator).
        </p>
      </div>
      <label className="block max-w-xl">
        <span className="mb-1 block text-xs text-ink-3">Filter by keyword</span>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="crash, tokens, approval, handoff…"
          className="w-full rounded-lg border border-line bg-surface-1 px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none"
        />
      </label>
      <p className="text-xs text-ink-3" aria-live="polite">
        {entries.length} of {catalog.guide.length} entries
      </p>
      {entries.length === 0 ? (
        <Card className="p-6 text-sm text-ink-2">
          Nothing matches “{q}”. Try a broader word, or{" "}
          <button type="button" className="text-accent-soft underline" onClick={() => setQ("")}>
            clear the filter
          </button>
          .
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {entries.map((e) => {
            const p = catalog.patterns.find((x) => x.id === e.pattern);
            const s = p?.solutions.find((x) => x.id === e.solution);
            return (
              <Card key={e.problem} className="flex flex-col p-5">
                <h2 className="text-base font-semibold leading-snug text-ink">{e.problem}</h2>
                <div className="mt-3">
                  <div className="text-xs font-semibold uppercase tracking-wider text-ink-3">Recommendation</div>
                  <p className="mt-1 text-sm leading-relaxed text-ink-2">{e.recommendation}</p>
                </div>
                <div className="mt-3 border-l-2 border-accent/60 pl-3">
                  <div className="text-xs font-semibold uppercase tracking-wider text-ink-3">Measured here</div>
                  <p className="mt-1 text-sm leading-relaxed text-ink-2">
                    <Inline text={e.evidence} />
                  </p>
                </div>
                {p && s ? (
                  <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 pt-1 text-sm">
                    <a className="text-accent-soft underline" href={href(["patterns", p.id], { s: s.id })}>
                      {s.name}
                    </a>
                    <a className="text-ink-3 underline hover:text-ink" href={href(["compare", p.id])}>
                      alternatives
                    </a>
                    <a className="text-ink-3 underline hover:text-ink" href={href(["results", p.experiment])}>
                      evidence
                    </a>
                  </div>
                ) : null}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
