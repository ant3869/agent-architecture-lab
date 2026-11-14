import { useState } from "react";
import { CodeBlock } from "../components/Code";
import { Diagram } from "../components/Diagram";
import { ResultsPanel } from "../components/ResultsPanel";
import { BulletList, Card, Inline, Pill, RichText, SectionTitle, StatusBadge } from "../components/ui";
import { href, navigate } from "../lib/router";
import type { Catalog, Results, Solution } from "../types";

function langOf(path: string): string {
  return path.endsWith(".ts") || path.endsWith(".tsx") ? "typescript" : "python";
}

function Facts({ s }: { s: Solution }) {
  const rows: [string, string | undefined][] = [
    ["Performance", s.performance],
    ["Complexity", s.complexity],
    ["Reliability", s.reliability],
    ["Security", s.security],
  ];
  const present = rows.filter((r): r is [string, string] => Boolean(r[1]));
  if (present.length === 0) return null;
  return (
    <dl className="grid gap-x-6 gap-y-4 md:grid-cols-2">
      {present.map(([k, v]) => (
        <div key={k}>
          <dt className="text-xs font-semibold uppercase tracking-wider text-ink-3">{k}</dt>
          <dd className="mt-1 text-sm leading-relaxed text-ink-2">
            <Inline text={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function PatternView({ catalog, results, id, solutionId }: { catalog: Catalog; results: Results; id: string; solutionId?: string }) {
  const pattern = catalog.patterns.find((p) => p.id === id);
  const [file, setFile] = useState<"implementation" | "example">("implementation");
  if (!pattern) {
    return (
      <p className="text-sm text-ink-2">
        No pattern called “{id}”.{" "}
        <a className="text-accent-soft underline" href="#/">
          See all patterns
        </a>
        .
      </p>
    );
  }
  const solution = pattern.solutions.find((s) => s.id === solutionId) ?? pattern.solutions[0];
  if (!solution) return <p className="text-sm text-ink-2">This pattern has no solutions yet.</p>;
  const exp = results.experiments[pattern.experiment];
  const traces = catalog.traces.filter((t) => t.pattern === pattern.id);
  const path = file === "implementation" ? solution.implementation : solution.example;
  const source = path ? catalog.code[path] : undefined;
  const sources = pattern.research.map((k) => catalog.sources.find((s) => s.key === k)).filter((s) => s !== undefined);

  return (
    <div className="space-y-6">
      <div>
        <a href="#/" className="text-sm text-ink-3 hover:text-ink">
          ← All patterns
        </a>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">{pattern.title}</h1>
        <p className="mt-1 text-base text-ink-2">{pattern.tagline}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <SectionTitle>Problem</SectionTitle>
          <p className="text-sm leading-relaxed text-ink-2">{pattern.problem.trim()}</p>
          <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-ink-3">Where it shows up</h3>
          <BulletList items={pattern.applications} />
        </Card>
        <Card className="border-accent/40 p-5">
          <SectionTitle hint="advice, not a measurement">Recommendation</SectionTitle>
          <p className="text-sm leading-relaxed text-ink-2">{pattern.decision.trim()}</p>
          <a href={href(["compare", pattern.id])} className="mt-4 inline-block text-sm text-accent-soft underline">
            Compare the alternatives side by side
          </a>
        </Card>
      </div>

      <Card className="p-5">
        <SectionTitle hint={`${pattern.solutions.length} alternatives`}>Solutions</SectionTitle>
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Solutions">
          {pattern.solutions.map((s) => (
            <Pill key={s.id} active={s.id === solution.id} onClick={() => navigate(["patterns", pattern.id], { s: s.id })}>
              <span aria-hidden className={`mr-1.5 ${s.status === "implemented" ? "text-good" : "text-ink-3"}`}>
                {s.status === "implemented" ? "●" : "○"}
              </span>
              {s.name}
            </Pill>
          ))}
        </div>

        <div className="mt-5 space-y-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="max-w-3xl">
              <h2 className="text-xl font-semibold text-ink">{solution.name}</h2>
              <p className="mt-1 text-sm leading-relaxed text-ink-2">{solution.summary}</p>
            </div>
            <StatusBadge kind={solution.status} />
          </div>

          {solution.diagram ? <Diagram source={solution.diagram} label={`Architecture diagram: ${solution.name}`} /> : null}

          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Advantages</h3>
              <BulletList items={solution.advantages} tone="plus" />
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Limitations</h3>
              <BulletList items={solution.limitations} tone="minus" />
            </div>
          </div>

          <Facts s={solution} />

          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Use when</h3>
              <BulletList items={solution.use_when} />
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Avoid when</h3>
              <BulletList items={solution.avoid_when} />
            </div>
          </div>

          {solution.integration ? (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Integration</h3>
              <RichText text={solution.integration} renderCode={(code, lang) => <CodeBlock code={code} lang={lang} />} />
            </div>
          ) : null}

          <p className="text-sm text-ink-3">
            <span className="font-medium text-ink-2">Where you have seen it: </span>
            {solution.frameworks}
          </p>

          {solution.implementation || solution.example ? (
            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-3">Runnable code</h3>
                <div className="flex gap-2">
                  {solution.implementation ? (
                    <Pill active={file === "implementation"} onClick={() => setFile("implementation")}>
                      Implementation
                    </Pill>
                  ) : null}
                  {solution.example ? (
                    <Pill active={file === "example"} onClick={() => setFile("example")}>
                      Example
                    </Pill>
                  ) : null}
                </div>
              </div>
              {path && source !== undefined ? <CodeBlock code={source} lang={langOf(path)} path={path} /> : <p className="text-sm text-ink-3">No file of this kind for this solution.</p>}
              {solution.tests ? (
                <p className="mt-2 text-xs text-ink-3">
                  Tests: <code className="font-mono text-ink-2">{solution.tests}</code>
                  {solution.example ? (
                    <>
                      {" · "}run: <code className="font-mono text-ink-2">python {solution.example}</code>
                    </>
                  ) : null}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </Card>

      {exp ? (
        <Card className="p-5">
          <SectionTitle hint={`n = ${catalog.manifest.n} · bars for “${solution.name}” are emphasised`}>Measured comparison</SectionTitle>
          <p className="mb-4 text-sm text-ink-2">{exp.question}</p>
          <ResultsPanel key={exp.id} exp={exp} highlight={solution.result_arch} compactMode />
          <a href={href(["results", exp.id])} className="mt-4 inline-block text-sm text-accent-soft underline">
            Test conditions and full experiment
          </a>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {traces.length > 0 ? (
          <Card className="p-5">
            <SectionTitle>Recorded traces</SectionTitle>
            <ul className="space-y-2">
              {traces.map((t) => (
                <li key={t.id}>
                  <a href={href(["traces", t.id])} className="block rounded-lg border border-line bg-surface-2 px-3 py-2 hover:border-accent/70">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-ink">{t.title}</span>
                      <StatusBadge kind={t.summary.outcome} />
                    </div>
                    <div className="mt-0.5 text-xs text-ink-3">
                      {t.events} events · {t.summary.model_calls} model calls · {t.summary.tokens.toLocaleString("en-US")} tokens
                    </div>
                  </a>
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
        <Card className="p-5">
          <SectionTitle>Research behind this pattern</SectionTitle>
          <ul className="space-y-2">
            {sources.map((s) => (
              <li key={s.key} className="text-sm leading-snug">
                <a href={s.url} target="_blank" rel="noreferrer" className="text-accent-soft underline decoration-accent/40 hover:decoration-accent">
                  {s.title}
                </a>
                <span className="text-ink-3">
                  {" "}
                  — {s.authors}, {s.year}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
