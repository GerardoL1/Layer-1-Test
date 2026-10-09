/**
 * Runs the Apple Health sync at the right moments and tells screens when it finished:
 *   - when the app starts (also when iOS starts it in the background for new data)
 *   - when the app comes back to the foreground
 *   - when HealthKit reports new data, a few seconds later so a burst becomes one sync
 * On the web all of this does nothing.
 */
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AppState } from 'react-native';

import { useSession } from '../state/session';
import { healthAvailable, syncHealth, SyncResult, watchHealth } from './health';

type HealthSync = {
  /** Changes every time a sync added new readings, so screens can reload. */
  dataVersion: number;
  syncing: boolean;
  lastResult: SyncResult | null;
  lastError: string | null;
  syncNow: () => Promise<void>;
};

const Ctx = createContext<HealthSync>({ dataVersion: 0, syncing: false, lastResult: null, lastError: null,
  syncNow: async () => {} });

const QUIET_MS = 5000;

export function HealthSyncProvider({ children }: { children: ReactNode }) {
  const { serverUrl, userId } = useSession();
  const [dataVersion, setDataVersion] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const [lastResult, setLastResult] = useState<SyncResult | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const syncNow = useCallback(async () => {
    if (!healthAvailable() || !serverUrl || !userId) return;
    setSyncing(true);
    try {
      const r = await syncHealth(serverUrl, userId);
      setLastResult(r);
      setLastError(null);
      if (r.added > 0) setDataVersion((v) => v + 1);
    } catch (e) {
      // Keep the app usable. The next sync reads the same data again.
      setLastError(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(false);
    }
  }, [serverUrl, userId]);

  useEffect(() => {
    if (!healthAvailable()) return;
    // Started from a HealthKit wake-up or by the person, either way read what's new.
    const first = setTimeout(syncNow, 0);
    const appState = AppState.addEventListener('change', (s) => {
      if (s === 'active') syncNow();
    });
    const stopWatching = watchHealth(() => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(syncNow, QUIET_MS);
    });
    return () => {
      clearTimeout(first);
      appState.remove();
      stopWatching();
      if (timer.current) clearTimeout(timer.current);
    };
  }, [syncNow]);

  const value = useMemo(() => ({ dataVersion, syncing, lastResult, lastError, syncNow }),
    [dataVersion, syncing, lastResult, lastError, syncNow]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useHealthSync = () => useContext(Ctx);
