import { useEffect, useId, useState } from "react";

type State = { kind: "loading" } | { kind: "ok"; svg: string } | { kind: "error"; message: string };

let mermaidReady: Promise<typeof import("mermaid").default> | null = null;

function loadMermaid() {
  mermaidReady ??= import("mermaid").then(({ default: mermaid }) => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "base",
      fontFamily: "ui-sans-serif, system-ui, sans-serif",
      themeVariables: {
        darkMode: true,
        background: "#1a1a19",
        primaryColor: "#242422",
        primaryTextColor: "#f0efec",
        primaryBorderColor: "#5598e7",
        secondaryColor: "#2e2e2b",
        tertiaryColor: "#1a1a19",
        lineColor: "#8f8e85",
        textColor: "#c3c2b7",
        edgeLabelBackground: "#1a1a19",
        actorBkg: "#242422",
        actorBorder: "#5598e7",
        actorTextColor: "#f0efec",
        signalColor: "#c3c2b7",
        signalTextColor: "#c3c2b7",
        labelBoxBkgColor: "#242422",
        labelBoxBorderColor: "#383835",
        labelTextColor: "#c3c2b7",
        noteBkgColor: "#2e2e2b",
        noteTextColor: "#f0efec",
        fontSize: "14px",
      },
    });
    return mermaid;
  });
  return mermaidReady;
}

/** Renders a Mermaid diagram. If rendering fails the source is shown instead, so information is never lost. */
export function Diagram({ source, label }: { source: string; label: string }) {
  const id = `mmd-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const [state, setState] = useState<State>({ kind: "loading" });
  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    loadMermaid()
      .then((mermaid) => mermaid.render(id, source.trim()))
      .then(({ svg }) => {
        if (!cancelled) setState({ kind: "ok", svg });
      })
      .catch((err: unknown) => {
        document.getElementById(`d${id}`)?.remove(); // mermaid leaves an error node behind
        if (!cancelled) setState({ kind: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [id, source]);

  if (state.kind === "ok") {
    return <div role="img" aria-label={label} data-diagram="ok" className="mermaid-host flex justify-center overflow-x-auto rounded-lg border border-line bg-surface-1 p-4" dangerouslySetInnerHTML={{ __html: state.svg }} />;
  }
  if (state.kind === "error") {
    return (
      <div data-diagram="error" className="rounded-lg border border-line bg-surface-1 p-4">
        <p className="mb-2 text-xs text-ink-3">Diagram could not be rendered ({state.message}). Source:</p>
        <pre className="overflow-x-auto font-mono text-xs text-ink-2">{source.trim()}</pre>
      </div>
    );
  }
  return <div data-diagram="loading" className="h-40 animate-pulse rounded-lg border border-line bg-surface-1" aria-busy="true" />;
}
