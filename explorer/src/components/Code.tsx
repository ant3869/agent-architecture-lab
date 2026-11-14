import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import typescript from "highlight.js/lib/languages/typescript";
import { useMemo, useState } from "react";

hljs.registerLanguage("python", python);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("bash", bash);

function highlight(code: string, lang: string): string {
  try {
    return hljs.highlight(code, { language: hljs.getLanguage(lang) ? lang : "python" }).value;
  } catch {
    return code.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] ?? c);
  }
}

export function CodeBlock({ code, lang = "python", path, maxHeight = "32rem" }: { code: string; lang?: string; path?: string; maxHeight?: string }) {
  const html = useMemo(() => highlight(code, lang), [code, lang]);
  const [copied, setCopied] = useState<"idle" | "ok" | "failed">("idle");
  const lines = code.split("\n").length;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied("ok");
    } catch {
      setCopied("failed");
    }
    window.setTimeout(() => setCopied("idle"), 1600);
  };
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-surface-0">
      <div className="flex items-center justify-between gap-3 border-b border-line bg-surface-2 px-3 py-1.5">
        <span className="truncate font-mono text-xs text-ink-2">{path ?? lang}</span>
        <span className="flex shrink-0 items-center gap-3 text-xs text-ink-3">
          {path ? <span>{lines} lines</span> : null}
          <button type="button" onClick={copy} className="rounded border border-line px-2 py-0.5 text-ink-2 hover:border-ink-3 hover:text-ink">
            {copied === "ok" ? "Copied" : copied === "failed" ? "Copy failed" : "Copy"}
          </button>
        </span>
      </div>
      <pre className="overflow-auto p-3 text-[12.5px] leading-[1.55]" style={{ maxHeight }} tabIndex={0}>
        <code className="font-mono text-ink" dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  );
}
