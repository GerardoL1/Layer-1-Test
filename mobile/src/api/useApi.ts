/**
 * Small hooks so screens can load data with one line and show loading / error states.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useSession } from '../state/session';
import { makeApi } from './client';

export function useApi() {
  const { serverUrl, userId } = useSession();
  return useMemo(() => makeApi(serverUrl, userId), [serverUrl, userId]);
}

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
      (e) => current && setResult((prev) => ({ key, run, data: prev.data,
        error: e instanceof Error ? e.message : String(e) })),
    );
    return () => {
      current = false;
    };
  }, [key, run]);

  const reload = useCallback(() => setRun((n) => n + 1), []);
  const loading = result.key !== key || result.run !== run;
  return { data: result.data, error: loading ? null : result.error, loading, reload };
}
