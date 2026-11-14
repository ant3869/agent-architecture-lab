import { useEffect, useState } from "react";
import type { Catalog, Results, Trace } from "../types";

const base = `${import.meta.env.BASE_URL}data/`;

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(base + path);
  if (!res.ok) {
    throw new Error(`Could not load ${path} (HTTP ${res.status}). Run "python scripts/build_catalog.py" to regenerate explorer data.`);
  }
  return (await res.json()) as T;
}

export type Loadable<T> = { state: "loading" } | { state: "error"; message: string; retry: () => void } | { state: "ready"; data: T };

/** Fetch JSON with loading, error and retry states. Re-fetches when `path` changes. */
export function useJson<T>(path: string | null): Loadable<T> {
  const [attempt, setAttempt] = useState(0);
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" });
  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setValue({ state: "loading" });
    getJson<T>(path)
      .then((data) => {
        if (!cancelled) setValue({ state: "ready", data });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setValue({ state: "error", message: err instanceof Error ? err.message : String(err), retry: () => setAttempt((a) => a + 1) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [path, attempt]);
  return value;
}

export const useCatalog = () => useJson<Catalog>("catalog.json");
export const useResults = () => useJson<Results>("results.json");
export const useTrace = (id: string | null) => useJson<Trace>(id ? `traces/${id}.json` : null);
