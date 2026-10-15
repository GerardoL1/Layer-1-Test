/**
 * Loads data for a screen with one line and keeps the loading and error states.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

type Result<T> = { key: unknown; run: number; data: T | null; error: string | null };

/**
 * Runs load() and keeps its result. It runs again whenever key changes
 * (for example the API object, or the chosen range on Trends), or when reload() is called.
 * The previous data stays on screen while a new load is running.
 */
export function useLoad<T>(load: () => Promise<T>, key: unknown) {
  const [run, setRun] = useState(0);
  const [result, setResult] = useState<Result<T>>({ key: undefined, run: -1, data: null, error: null });
  // Always call the newest load function without making it a dependency.
  const latest = useRef(load);
  useEffect(() => {
    latest.current = load;
  });

  useEffect(() => {
    let current = true;   // ignore answers that arrive after the screen moved on
    latest.current().then(
      (data) => current && setResult({ key, run, data, error: null }),
      (e) => current && setResult((prev) => ({ key, run, data: prev.data, error: errorText(e) })),
    );
    return () => {
      current = false;
    };
  }, [key, run]);

  const reload = useCallback(() => setRun((n) => n + 1), []);
  const loading = result.key !== key || result.run !== run;
  return { data: result.data, error: loading ? null : result.error, loading, reload };
}

/** The message to show for anything thrown. */
export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
