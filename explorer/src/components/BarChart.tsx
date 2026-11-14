import { useState } from "react";
import { compact, formatValue, isPercentKey } from "../lib/format";
import type { Row } from "../types";

interface Props {
  rows: Row[];
  metric: string;
  metricLabel: string;
  highlight?: string[];
}

/**
 * Horizontal bars, one per architecture, one measure, one axis.
 * Identity is carried by the row label, so every bar wears the same series colour;
 * `highlight` marks the rows that belong to the solution being viewed.
 */
export function BarChart({ rows, metric, metricLabel, highlight }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const values = rows.map((r) => (typeof r[metric] === "number" ? (r[metric] as number) : 0));
  const percent = isPercentKey(metric);
  const max = percent ? 1 : Math.max(...values, 0) || 1;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  return (
    <figure className="m-0" aria-label={`${metricLabel} by architecture`}>
      <div className="grid grid-cols-[minmax(6.5rem,38%)_1fr] gap-x-3 sm:grid-cols-[minmax(9rem,16rem)_1fr]">
        <div />
        <div className="relative h-5 text-[11px] tabular-nums text-ink-3">
          {ticks.map((t, i) => (
            <span key={i} className="absolute -translate-x-1/2" style={{ left: `${(t / max) * 100}%`, transform: i === 0 ? "none" : i === ticks.length - 1 ? "translateX(-100%)" : undefined }}>
              {percent ? `${Math.round(t * 100)}%` : compact(t)}
            </span>
          ))}
        </div>
        {rows.map((r, i) => {
          const v = values[i] ?? 0;
          const frac = Math.max(0, Math.min(1, v / max));
          const dim = highlight && highlight.length > 0 && !highlight.includes(r.arch);
          const ci = metric === "success_rate" && Array.isArray(r.success_ci95) ? (r.success_ci95 as number[]) : null;
          const labelInside = frac > 0.85;
          return (
            <div key={`${r.scenario}-${r.arch}`} className="contents" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <div className={`flex min-w-0 items-center justify-end py-1 text-right text-[13px] leading-tight [overflow-wrap:anywhere] ${dim ? "text-ink-3" : "text-ink-2"}`}>{r.arch}</div>
              <div className="relative flex items-center py-1" tabIndex={0} onFocus={() => setHover(i)} onBlur={() => setHover(null)} aria-label={`${r.arch}: ${formatValue(metric, v)}`}>
                <div className="pointer-events-none absolute inset-y-0 left-0 right-0">
                  {ticks.map((t, k) => (
                    <span key={k} className="absolute inset-y-0 w-px bg-line/70" style={{ left: `${(t / max) * 100}%` }} />
                  ))}
                </div>
                <div className={`relative h-[18px] rounded-r-[4px] ${dim ? "bg-series-1/35" : "bg-series-1"}`} style={{ width: `${frac * 100}%`, minWidth: v > 0 ? 2 : 0 }} />
                <span className={`relative whitespace-nowrap text-xs tabular-nums ${labelInside ? "-ml-1 -translate-x-full pr-1.5 text-white" : "ml-1.5 text-ink-2"}`}>{formatValue(metric, v)}</span>
                {hover === i ? (
                  <div role="tooltip" className="pointer-events-none absolute left-2 top-full z-20 mt-0.5 min-w-52 rounded-md border border-line bg-surface-3 px-3 py-2 text-xs shadow-xl">
                    <div className="font-medium text-ink">{r.arch}</div>
                    <div className="mt-1 flex justify-between gap-4 text-ink-2">
                      <span>{metricLabel}</span>
                      <span className="tabular-nums text-ink">{formatValue(metric, v)}</span>
                    </div>
                    {ci ? (
                      <div className="flex justify-between gap-4 text-ink-3">
                        <span>95% interval (Wilson)</span>
                        <span className="tabular-nums">
                          {((ci[0] ?? 0) * 100).toFixed(0)}–{((ci[1] ?? 0) * 100).toFixed(0)}%
                        </span>
                      </div>
                    ) : null}
                    {typeof r.n === "number" ? (
                      <div className="flex justify-between gap-4 text-ink-3">
                        <span>Runs</span>
                        <span className="tabular-nums">{r.n}</span>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </figure>
  );
}
