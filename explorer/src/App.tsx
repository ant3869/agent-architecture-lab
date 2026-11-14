import { Component, type ErrorInfo, type ReactNode } from "react";
import { Load } from "./components/ui";
import { useCatalog, useResults } from "./lib/data";
import { href, useRoute } from "./lib/router";
import type { Catalog, Results } from "./types";
import { CompareView } from "./views/CompareView";
import { GuideView } from "./views/GuideView";
import { Overview } from "./views/Overview";
import { PatternView } from "./views/PatternView";
import { ResultsView } from "./views/ResultsView";
import { SourcesView } from "./views/SourcesView";
import { TracesView } from "./views/TracesView";

const NAV = [
  { id: "", label: "Patterns" },
  { id: "compare", label: "Compare" },
  { id: "results", label: "Results" },
  { id: "traces", label: "Traces" },
  { id: "guide", label: "Guide" },
  { id: "sources", label: "Sources" },
];

class ErrorBoundary extends Component<{ children: ReactNode; resetKey: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("view crashed", error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (this.state.error) {
      return (
        <div role="alert" className="m-6 rounded-lg border border-critical/50 bg-critical/10 p-5 text-sm">
          <p className="font-medium text-ink">This view failed to render.</p>
          <p className="mt-1 text-ink-2">{this.state.error.message}</p>
          <a href="#/" className="mt-3 inline-block text-accent-soft underline">
            Back to the pattern list
          </a>
        </div>
      );
    }
    return this.props.children;
  }
}

function View({ catalog, results, parts, query }: { catalog: Catalog; results: Results; parts: string[]; query: Record<string, string> }) {
  switch (parts[0] ?? "") {
    case "":
      return <Overview catalog={catalog} results={results} />;
    case "patterns":
      return <PatternView catalog={catalog} results={results} id={parts[1] ?? ""} solutionId={query.s} />;
    case "compare":
      return <CompareView catalog={catalog} results={results} id={parts[1]} />;
    case "results":
      return <ResultsView catalog={catalog} results={results} id={parts[1]} />;
    case "traces":
      return <TracesView catalog={catalog} id={parts[1]} />;
    case "guide":
      return <GuideView catalog={catalog} />;
    case "sources":
      return <SourcesView catalog={catalog} />;
    default:
      return (
        <div className="p-8 text-sm text-ink-2">
          Nothing lives at this address.{" "}
          <a className="text-accent-soft underline" href="#/">
            Go to the pattern list
          </a>
          .
        </div>
      );
  }
}

export function App() {
  const route = useRoute();
  const catalog = useCatalog();
  const results = useResults();
  const section = route.parts[0] === "patterns" ? "" : (route.parts[0] ?? "");
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line bg-surface-0/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <a href="#/" className="flex items-center gap-2.5 font-semibold tracking-tight text-ink">
            <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden className="text-accent">
              <circle cx="5" cy="12" r="2.6" fill="currentColor" />
              <circle cx="19" cy="5" r="2.6" fill="currentColor" opacity="0.75" />
              <circle cx="19" cy="19" r="2.6" fill="currentColor" opacity="0.5" />
              <path d="M7.4 11 16.6 6M7.4 13l9.2 5" stroke="currentColor" strokeWidth="1.6" fill="none" />
            </svg>
            Agent Architecture Lab
          </a>
          <nav aria-label="Sections" className="flex flex-wrap gap-1">
            {NAV.map((n) => (
              <a
                key={n.id}
                href={href(n.id ? [n.id] : [])}
                aria-current={section === n.id ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm transition-colors ${section === n.id ? "bg-surface-2 text-ink" : "text-ink-2 hover:bg-surface-1 hover:text-ink"}`}
              >
                {n.label}
              </a>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <ErrorBoundary resetKey={route.parts.join("/")}>
          <Load value={catalog}>{(c) => <Load value={results}>{(r) => <View catalog={c} results={r} parts={route.parts} query={route.query} />}</Load>}</Load>
        </ErrorBoundary>
      </main>
      <footer className="mx-auto max-w-7xl px-4 pb-10 pt-4 text-xs leading-relaxed text-ink-3 sm:px-6">
        Numbers on this site are measured by running the reference implementations against a deterministic simulator. They compare architectures under stated assumptions; they are not benchmarks of any language model.
      </footer>
    </div>
  );
}
