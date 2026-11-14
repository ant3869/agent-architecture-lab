import { useState } from "react";
import { BulletList, Card, Inline, Pill, SectionTitle, StatusBadge } from "../components/ui";
import { formatValue } from "../lib/format";
import { href, navigate } from "../lib/router";
import type { Catalog, Experiment, Results, Row, Solution } from "../types";

function measured(exp: Experiment | undefined, s: Solution, scenario: string): Row | undefined {
  const arch = s.result_arch?.[0];
  return exp?.rows.find((r) => r.arch === arch && r.scenario === scenario) ?? exp?.rows.find((r) => r.arch === arch);
}

/** Side-by-side matrix: one column per alternative, qualitative rows first, measured rows last. */
export function CompareView({ catalog, results, id }: { catalog: Catalog; results: Results; id?: string }) {
  const pattern = catalog.patterns.find((p) => p.id === id) ?? catalog.patterns[0];
  const exp = pattern ? results.experiments[pattern.experiment] : undefined;
  const scenarios = exp ? [...new Set(exp.rows.map((r) => r.scenario))] : [];
  const [scenario, setScenario] = useState<string>("");
  if (!pattern) return <p className="text-sm text-ink-2">The catalogue is empty.</p>;
  const active = scenarios.includes(scenario) ? scenario : (scenarios[0] ?? "");
  const sols = pattern.solutions;
  const metricCols = exp ? exp.columns.filter((c) => c.key !== "arch" && c.key !== "file" && c.key !== "n") : [];
  const cell = "border-t border-line px-4 py-3 align-top";
  const text = (v: string | undefined) => (v ? <Inline text={v} /> : <span className="text-ink-3">—</span>);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Compare alternatives</h1>
        <p className="mt-1 text-sm text-ink-2">Pick a problem. Each column is one way to solve it.</p>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Problem">
        {catalog.patterns.map((p) => (
          <Pill key={p.id} active={p.id === pattern.id} onClick={() => navigate(["compare", p.id])}>
            {p.title}
          </Pill>
        ))}
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full min-w-[56rem] table-fixed text-left text-sm">
          <colgroup>
            <col className="w-40" />
            {sols.map((s) => (
              <col key={s.id} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th className="px-4 py-3" />
              {sols.map((s) => (
                <th key={s.id} scope="col" className="px-4 py-3 align-top font-normal">
                  <a href={href(["patterns", pattern.id], { s: s.id })} className="text-base font-semibold text-ink hover:text-accent-soft">
                    {s.name}
                  </a>
                  <div className="mt-1.5">
                    <StatusBadge kind={s.status} />
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-ink-2">
            <tr>
              <th scope="row" className={`${cell} text-xs font-semibold uppercase tracking-wider text-ink-3`}>
                In one line
              </th>
              {sols.map((s) => (
                <td key={s.id} className={cell}>
                  {s.summary}
                </td>
              ))}
            </tr>
            {(
              [
                ["Advantages", (s: Solution) => <BulletList items={s.advantages} tone="plus" />],
                ["Limitations", (s: Solution) => <BulletList items={s.limitations} tone="minus" />],
                ["Performance", (s: Solution) => text(s.performance)],
                ["Complexity", (s: Solution) => text(s.complexity)],
                ["Reliability", (s: Solution) => text(s.reliability)],
                ["Security", (s: Solution) => text(s.security)],
                ["Use when", (s: Solution) => <BulletList items={s.use_when} />],
                ["Avoid when", (s: Solution) => <BulletList items={s.avoid_when} />],
                ["Seen in", (s: Solution) => text(s.frameworks)],
              ] as [string, (s: Solution) => React.ReactNode][]
            ).map(([label, render]) => (
              <tr key={label}>
                <th scope="row" className={`${cell} text-xs font-semibold uppercase tracking-wider text-ink-3`}>
                  {label}
                </th>
                {sols.map((s) => (
                  <td key={s.id} className={`${cell} leading-relaxed`}>
                    {render(s)}
                  </td>
                ))}
              </tr>
            ))}
            <tr>
              <th scope="row" className={`${cell} text-xs font-semibold uppercase tracking-wider text-ink-3`}>
                Code
              </th>
              {sols.map((s) => (
                <td key={s.id} className={`${cell} break-all font-mono text-xs`}>
                  {s.implementation ? (
                    <a className="text-accent-soft underline" href={href(["patterns", pattern.id], { s: s.id })}>
                      {s.implementation}
                    </a>
                  ) : (
                    <span className="font-sans text-ink-3">not implemented</span>
                  )}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </Card>

      {exp ? (
        <Card className="p-5">
          <SectionTitle hint={`experiment “${exp.id}”, n = ${catalog.manifest.n}`}>Measured, same scenario for every column</SectionTitle>
          <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Scenario">
            {scenarios.map((sc) => (
              <Pill key={sc} active={sc === active} onClick={() => setScenario(sc)}>
                {sc}
              </Pill>
            ))}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="text-xs text-ink-3">
                <tr>
                  <th className="py-2 pr-4 font-medium">Metric</th>
                  {sols.map((s) => (
                    <th key={s.id} scope="col" className="px-3 py-2 text-right font-medium">
                      {s.name}
                      <div className="font-mono text-[11px] font-normal text-ink-3">{measured(exp, s, active)?.arch ?? "no data"}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metricCols.map((c) => (
                  <tr key={c.key} className="border-t border-line">
                    <th scope="row" className="py-2 pr-4 font-normal text-ink-2">
                      {c.label}
                    </th>
                    {sols.map((s) => {
                      const row = measured(exp, s, active);
                      return (
                        <td key={s.id} className="px-3 py-2 text-right tabular-nums text-ink">
                          {row && c.key in row ? formatValue(c.key, row[c.key]) : <span className="text-ink-3">—</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-ink-3">
            Each column shows the first result series mapped to that solution; where a column's series does not exist in the selected scenario, its closest scenario is shown and named under the heading.{" "}
            <a className="text-accent-soft underline" href={href(["results", exp.id])}>
              All series and conditions
            </a>
            .
          </p>
        </Card>
      ) : null}
    </div>
  );
}
