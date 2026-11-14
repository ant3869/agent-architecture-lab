import type { ReactNode } from "react";
import type { Loadable } from "../lib/data";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`min-w-0 rounded-xl border border-line bg-surface-1 ${className}`}>{children}</section>;
}

export function SectionTitle({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-3">{children}</h2>
      {hint ? <span className="text-xs text-ink-3">{hint}</span> : null}
    </div>
  );
}

const STATUS: Record<string, { label: string; icon: string; cls: string }> = {
  implemented: { label: "Implemented and tested", icon: "●", cls: "text-good" },
  documented: { label: "Documented only", icon: "○", cls: "text-ink-3" },
  ok: { label: "Goal met", icon: "✓", cls: "text-good" },
  wrong_effect: { label: "Wrong side effect", icon: "✕", cls: "text-critical" },
  duplicate_effect: { label: "Duplicate side effect", icon: "✕", cls: "text-critical" },
  incomplete: { label: "Incomplete", icon: "!", cls: "text-warning" },
  exfiltration: { label: "Data exfiltrated", icon: "✕", cls: "text-critical" },
  content: { label: "Content checked", icon: "✓", cls: "text-good" },
  reachable: { label: "URL reachable", icon: "◐", cls: "text-warning" },
  unverified: { label: "Not verified", icon: "!", cls: "text-serious" },
};

/** Status is always icon + words; colour is on the icon only, never the sole carrier. */
export function StatusBadge({ kind, label }: { kind: string; label?: string }) {
  const s = STATUS[kind] ?? { label: kind, icon: "•", cls: "text-ink-3" };
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-0.5 text-xs text-ink-2">
      <span aria-hidden className={s.cls}>
        {s.icon}
      </span>
      {label ?? s.label}
    </span>
  );
}

export function Pill({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm transition-colors ${
        active ? "border-accent bg-accent/15 text-ink" : "border-line bg-surface-2 text-ink-2 hover:border-ink-3 hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface-1 px-4 py-3">
      <div className="text-xs text-ink-3">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-ink">{value}</div>
      {sub ? <div className="mt-0.5 text-xs text-ink-3">{sub}</div> : null}
    </div>
  );
}

export function BulletList({ items, tone }: { items: string[]; tone?: "plus" | "minus" }) {
  const mark = tone === "plus" ? "+" : tone === "minus" ? "−" : "•";
  const cls = tone === "plus" ? "text-good" : tone === "minus" ? "text-serious" : "text-ink-3";
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item} className="flex min-w-0 gap-2 text-sm leading-relaxed text-ink-2 [overflow-wrap:anywhere]">
          <span aria-hidden className={`w-3 shrink-0 font-mono ${cls}`}>
            {mark}
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function Load<T>({ value, children }: { value: Loadable<T>; children: (data: T) => ReactNode }) {
  if (value.state === "loading") {
    return (
      <div role="status" className="flex items-center gap-3 p-8 text-sm text-ink-3">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
        Loading…
      </div>
    );
  }
  if (value.state === "error") {
    return (
      <div role="alert" className="m-4 rounded-lg border border-critical/50 bg-critical/10 p-4 text-sm text-ink">
        <p className="font-medium">Something went wrong loading data.</p>
        <p className="mt-1 text-ink-2">{value.message}</p>
        <button type="button" onClick={value.retry} className="mt-3 rounded-md border border-line bg-surface-2 px-3 py-1.5 text-sm hover:border-ink-3">
          Try again
        </button>
      </div>
    );
  }
  return <>{children(value.data)}</>;
}

/** Renders prose containing `inline code` and fenced ``` blocks. Not a Markdown engine. */
export function RichText({ text, renderCode }: { text: string; renderCode: (code: string, lang: string) => ReactNode }) {
  const parts = text.split(/```(\w*)\n([\s\S]*?)```/g);
  const out: ReactNode[] = [];
  for (let i = 0; i < parts.length; i += 3) {
    const prose = parts[i]?.trim();
    if (prose) {
      out.push(
        <p key={`p${i}`} className="text-sm leading-relaxed text-ink-2">
          <Inline text={prose} />
        </p>,
      );
    }
    const code = parts[i + 2];
    if (code !== undefined) out.push(<div key={`c${i}`}>{renderCode(code.replace(/\n$/, ""), parts[i + 1] || "python")}</div>);
  }
  return <div className="space-y-3">{out}</div>;
}

export function Inline({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`]+`)/g).map((seg, i) =>
        seg.startsWith("`") && seg.endsWith("`") ? (
          <code key={i} className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[0.85em] text-ink [overflow-wrap:anywhere]">
            {seg.slice(1, -1)}
          </code>
        ) : (
          <span key={i}>{seg}</span>
        ),
      )}
    </>
  );
}
