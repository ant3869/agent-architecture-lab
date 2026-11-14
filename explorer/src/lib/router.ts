import { useEffect, useState } from "react";

/** Minimal hash router: "#/patterns/execution-loops?s=react" -> { parts: ["patterns","execution-loops"], query: {s:"react"} } */
export interface Route {
  parts: string[];
  query: Record<string, string>;
}

function parse(hash: string): Route {
  const [path = "", qs = ""] = hash.replace(/^#\/?/, "").split("?");
  const query: Record<string, string> = {};
  new URLSearchParams(qs).forEach((v, k) => {
    query[k] = v;
  });
  return { parts: path.split("/").filter(Boolean).map(decodeURIComponent), query };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parse(window.location.hash));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function href(parts: string[], query: Record<string, string | undefined> = {}): string {
  const qs = new URLSearchParams(Object.entries(query).filter((e): e is [string, string] => e[1] !== undefined)).toString();
  return `#/${parts.map(encodeURIComponent).join("/")}${qs ? `?${qs}` : ""}`;
}

export function navigate(parts: string[], query: Record<string, string | undefined> = {}): void {
  window.location.hash = href(parts, query).slice(1);
}
