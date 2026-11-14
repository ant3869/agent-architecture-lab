import { useMemo, useState } from "react";
import { Card, Pill, StatusBadge } from "../components/ui";
import type { Catalog } from "../types";

export function SourcesView({ catalog }: { catalog: Catalog }) {
  const kinds = useMemo(() => ["all", ...new Set(catalog.sources.map((s) => s.kind))], [catalog.sources]);
  const [kind, setKind] = useState("all");
  const [q, setQ] = useState("");
  const rows = catalog.sources.filter((s) => (kind === "all" || s.kind === kind) && (q.trim() === "" || `${s.title} ${s.authors} ${s.note} ${s.key}`.toLowerCase().includes(q.trim().toLowerCase())));
  const v = catalog.verification;
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">Sources</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-2">
          Every claim in the research notes cites one of these.
          {v ? ` ${v.ok} of ${v.total} were checked automatically on ${v.checked_on}` : ""}
          {v && v.failed.length > 0 ? `; could not be fetched: ${v.failed.join(", ")}.` : v ? "." : ""}
        </p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Kind">
          {kinds.map((k) => (
            <Pill key={k} active={k === kind} onClick={() => setKind(k)}>
              {k}
            </Pill>
          ))}
        </div>
        <label className="ml-auto block w-full max-w-xs">
          <span className="sr-only">Search sources</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title, author, claim…" className="w-full rounded-lg border border-line bg-surface-1 px-3 py-1.5 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none" />
        </label>
      </div>
      <Card className="overflow-x-auto">
        {rows.length === 0 ? (
          <p className="p-6 text-sm text-ink-2">No sources match. Clear the search or pick “all”.</p>
        ) : (
          <table className="w-full min-w-[52rem] text-left text-sm">
            <thead className="bg-surface-2 text-xs text-ink-3">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Source</th>
                <th scope="col" className="px-4 py-2 font-medium">Cited for</th>
                <th scope="col" className="px-4 py-2 font-medium">Checked</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.key} className="border-t border-line align-top">
                  <td className="px-4 py-3">
                    <a href={s.url} target="_blank" rel="noreferrer" className="text-accent-soft underline decoration-accent/40 hover:decoration-accent">
                      {s.title}
                    </a>
                    <div className="mt-0.5 text-xs text-ink-3">
                      {s.authors} · {s.year} · {s.kind}
                      {s.arxiv ? ` · arXiv:${s.arxiv}` : ""}
                    </div>
                  </td>
                  <td className="max-w-md px-4 py-3 text-[13px] leading-relaxed text-ink-2">{s.note}</td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <StatusBadge kind={s.verified} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
