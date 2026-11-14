import { Card, Stat, StatusBadge } from "../components/ui";
import { href } from "../lib/router";
import type { Catalog, Results } from "../types";

export function Overview({ catalog, results }: { catalog: Catalog; results: Results }) {
  const implemented = catalog.patterns.flatMap((p) => p.solutions).filter((s) => s.status === "implemented").length;
  const runs = Object.values(results.experiments).reduce((a, e) => a + e.rows.reduce((b, r) => b + (typeof r.n === "number" ? r.n : 0), 0), 0);
  return (
    <div className="space-y-8">
      <section className="max-w-3xl">
        <h1 className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Which agent architecture fits this problem?</h1>
        <p className="mt-3 text-base leading-relaxed text-ink-2">
          A catalogue of agent execution, orchestration and reliability patterns. Every entry states the problem, gives at least three alternatives, links to a tested implementation, and shows what was measured when the alternatives ran the same scenarios.
        </p>
        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          <a href={href(["guide"])} className="rounded-md bg-accent px-4 py-2 font-medium text-white hover:brightness-110">
            Start from your problem
          </a>
          <a href={href(["results"])} className="rounded-md border border-line bg-surface-1 px-4 py-2 text-ink-2 hover:border-ink-3 hover:text-ink">
            See the measurements
          </a>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Engineering problems" value={catalog.patterns.length} />
        <Stat label="Implemented solutions" value={implemented} sub="each with example and tests" />
        <Stat label="Simulated runs behind the results" value={runs.toLocaleString("en-US")} sub={`digest ${catalog.manifest.digest.slice(0, 10)}`} />
        <Stat label="Cited sources" value={catalog.sources.length} sub={catalog.verification ? `${catalog.verification.ok} checked on ${catalog.verification.checked_on}` : undefined} />
      </div>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-3">Patterns</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {catalog.patterns.map((p) => (
            <a key={p.id} href={href(["patterns", p.id])} className="group block min-w-0 rounded-xl focus-visible:outline-offset-4">
              <Card className="h-full p-5 transition-colors group-hover:border-accent/70">
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="min-w-0 text-lg font-semibold text-ink">{p.title}</h3>
                  <span className="font-mono text-xs text-ink-3">{String(p.order).padStart(2, "0")}</span>
                </div>
                <p className="mt-1 text-sm leading-relaxed text-ink-2">{p.tagline}</p>
                <ul className="mt-4 space-y-1.5">
                  {p.solutions.map((s) => (
                    <li key={s.id} className="flex min-w-0 items-center gap-2 text-[13px] text-ink-2">
                      <span aria-hidden className={s.status === "implemented" ? "text-good" : "text-ink-3"}>
                        {s.status === "implemented" ? "●" : "○"}
                      </span>
                      <span className="min-w-0 truncate">{s.name}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            </a>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <StatusBadge kind="implemented" />
          <StatusBadge kind="documented" label="Documented for comparison, not implemented" />
        </div>
      </section>
    </div>
  );
}
