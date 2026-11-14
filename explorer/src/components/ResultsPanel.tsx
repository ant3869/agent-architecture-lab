import { useMemo, useState } from "react";
import { formatValue, numericKeys } from "../lib/format";
import type { Experiment, Row } from "../types";
import { BarChart } from "./BarChart";
import { BulletList, Inline, Pill } from "./ui";

/** One experiment: metric switcher, a bar chart per scenario, a table view, findings and limitations. */
export function ResultsPanel({ exp, highlight, compactMode = false }: { exp: Experiment; highlight?: string[]; compactMode?: boolean }) {
  const metricCols = useMemo(() => exp.columns.filter((c) => numericKeys(exp.rows, [c.key]).length > 0 && c.key !== "n"), [exp]);
  const [metric, setMetric] = useState<string>(metricCols[0]?.key ?? "");
  const [view, setView] = useState<"chart" | "table">("chart");
  const groups = useMemo(() => {
    const m = new Map<string, Row[]>();
    for (const r of exp.rows) {
      const k = exp.group_by.map((g) => String(r[g])).join(" / ");
      m.set(k, [...(m.get(k) ?? []), r]);
    }
    return [...m.entries()];
  }, [exp]);
  const active = metricCols.find((c) => c.key === metric) ?? metricCols[0];
  if (!active) return <p className="text-sm text-ink-3">This experiment has no numeric columns.</p>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Metric">
          {metricCols.map((c) => (
            <Pill key={c.key} active={c.key === active.key} onClick={() => setMetric(c.key)}>
              {c.label}
            </Pill>
          ))}
        </div>
        <div className="flex gap-2" role="group" aria-label="View">
          <Pill active={view === "chart"} onClick={() => setView("chart")}>
            Chart
          </Pill>
          <Pill active={view === "table"} onClick={() => setView("table")}>
            Table
          </Pill>
        </div>
      </div>

      <div className={compactMode ? "grid grid-cols-1 gap-5 xl:grid-cols-2" : "space-y-6"}>
        {groups.map(([name, rows]) => (
          <div key={name} className="min-w-0">
            <h4 className="mb-2 text-sm font-medium text-ink">{name}</h4>
            {view === "chart" ? (
              <BarChart rows={rows} metric={active.key} metricLabel={active.label} highlight={highlight} />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-line">
                <table className="w-full min-w-max text-left text-[13px]">
                  <thead className="bg-surface-2 text-xs text-ink-3">
                    <tr>
                      {exp.columns.filter((c) => rows.some((r) => c.key in r)).map((c) => (
                        <th key={c.key} scope="col" className={`px-3 py-2 font-medium ${c.key === "arch" || c.key === "file" ? "" : "text-right"}`}>
                          {c.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.arch} className="border-t border-line">
                        {exp.columns.filter((c) => rows.some((x) => c.key in x)).map((c) => (
                          <td key={c.key} className={`px-3 py-1.5 ${c.key === "arch" ? "text-ink" : c.key === "file" ? "font-mono text-xs text-ink-3" : "text-right tabular-nums text-ink-2"}`}>
                            {formatValue(c.key, r[c.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="min-w-0">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Measured findings</h4>
          <ul className="space-y-2">
            {exp.findings.map((f) => (
              <li key={f} className="border-l-2 border-accent/60 pl-3 text-sm leading-relaxed text-ink-2">
                <Inline text={f} />
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Limitations of this experiment</h4>
          <BulletList items={exp.limitations} />
        </div>
      </div>
    </div>
  );
}
