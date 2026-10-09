/**
 * Apple Health on iPhone. Metro picks this file on iOS and health.ts everywhere else,
 * so the web version never loads HealthKit.
 *
 * Sync is incremental: HealthKit gives each data type an "anchor" that marks what we
 * have already read. Each sync asks only for what changed since then, sends it to the
 * server, and saves the new anchor only after the server accepted it. If anything fails,
 * the next sync simply reads the same data again (the server ignores repeats).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  configureBackgroundTypes,
  isHealthDataAvailable,
  isProtectedDataAvailable,
  queryCategorySamplesWithAnchor,
  queryQuantitySamplesWithAnchor,
  requestAuthorization,
  subscribeToChanges,
  UpdateFrequency,
} from '@kingstinct/react-native-healthkit';

import { chunks, toUploadSample, toUploadStage, UploadSample, UploadStage } from './convert';

const QUANTITY = [
  { id: 'HKQuantityTypeIdentifierHeartRate', metric: 'heart_rate', unit: 'count/min' },
  { id: 'HKQuantityTypeIdentifierRestingHeartRate', metric: 'resting_heart_rate', unit: 'count/min' },
  { id: 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN', metric: 'hrv_sdnn', unit: 'ms' },
] as const;
const SLEEP = 'HKCategoryTypeIdentifierSleepAnalysis' as const;
const ALL_TYPES = [...QUANTITY.map((q) => q.id), SLEEP];

// The first sync reads this far back. Later syncs only read what's new.
const FIRST_SYNC_DAYS = 90;
// HealthKit hands back at most this many samples per call, and we upload in pieces this size.
const PAGE = 5000;
const UPLOAD_SIZE = 2000;

type SyncState = { since: string; anchors: Record<string, string> };

// One saved state per server and tester, so switching tester starts a fresh first sync.
const stateKey = (serverUrl: string, userId: string) => `recovery.healthsync.v1|${serverUrl}|${userId}`;

async function loadState(serverUrl: string, userId: string): Promise<SyncState> {
  try {
    const text = await AsyncStorage.getItem(stateKey(serverUrl, userId));
    if (text) return JSON.parse(text);
  } catch {
    // unreadable saved state, start over (the server ignores repeats)
  }
  return { since: new Date(Date.now() - FIRST_SYNC_DAYS * 86400000).toISOString(), anchors: {} };
}

const saveState = (serverUrl: string, userId: string, state: SyncState) =>
  AsyncStorage.setItem(stateKey(serverUrl, userId), JSON.stringify(state));

export const healthAvailable = () => isHealthDataAvailable();

/** Asks for permission to read the four types, and turns on background delivery. */
export async function connectHealth(): Promise<void> {
  await requestAuthorization({ toRead: ALL_TYPES });
  // Lets iOS wake the app when the watch saves new data. Apple decides the real timing,
  // usually once the phone is unlocked and charging, at most about once an hour.
  await configureBackgroundTypes(ALL_TYPES, UpdateFrequency.hourly);
}

async function upload(serverUrl: string, userId: string, samples: UploadSample[], sleep: UploadStage[]) {
  let added = 0;
  for (const part of chunks(samples, UPLOAD_SIZE)) added += await post(serverUrl, { user_id: userId, samples: part });
  for (const part of chunks(sleep, UPLOAD_SIZE)) added += await post(serverUrl, { user_id: userId, sleep: part });
  return added;
}

async function post(serverUrl: string, body: object): Promise<number> {
  const res = await fetch(`${serverUrl.replace(/\/+$/, '')}/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Server replied ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // not JSON
    }
    throw new Error(detail);
  }
  return (await res.json()).new as number;
}

export type SyncResult = { read: number; added: number; message: string };

let running: Promise<SyncResult> | null = null;

/** Reads what's new in Apple Health and sends it. Calls made while one is running share it. */
export function syncHealth(serverUrl: string, userId: string): Promise<SyncResult> {
  if (!running) {
    running = doSync(serverUrl, userId).finally(() => {
      running = null;
    });
  }
  return running;
}

async function doSync(serverUrl: string, userId: string): Promise<SyncResult> {
  if (!serverUrl || !userId) return { read: 0, added: 0, message: 'Pick a server and tester first.' };
  // Health data is locked while the phone is locked. Try again when it's unlocked.
  if (!isProtectedDataAvailable()) return { read: 0, added: 0, message: 'Phone is locked, will sync later.' };

  const state = await loadState(serverUrl, userId);
  const filter = { date: { startDate: new Date(state.since) } };
  let read = 0;
  let added = 0;

  for (const q of QUANTITY) {
    // Keep reading pages until HealthKit has nothing more for this type.
    for (;;) {
      const r = await queryQuantitySamplesWithAnchor(q.id, { limit: PAGE, unit: q.unit, filter,
        anchor: state.anchors[q.id] });
      const samples = r.samples.map((s) => toUploadSample(q.metric, s));
      added += await upload(serverUrl, userId, samples, []);
      read += samples.length;
      state.anchors[q.id] = r.newAnchor;
      await saveState(serverUrl, userId, state);
      if (r.samples.length < PAGE) break;
    }
  }
  for (;;) {
    const r = await queryCategorySamplesWithAnchor(SLEEP, { limit: PAGE, filter, anchor: state.anchors[SLEEP] });
    const stages = r.samples.map((s) => toUploadStage(s as never)).filter((s): s is UploadStage => s !== null);
    added += await upload(serverUrl, userId, [], stages);
    read += r.samples.length;
    state.anchors[SLEEP] = r.newAnchor;
    await saveState(serverUrl, userId, state);
    if (r.samples.length < PAGE) break;
  }
  // HealthKit also reports deleted samples. The server can't remove readings yet, so they're
  // skipped. Deleting watch data is rare and the next night's results aren't affected much.

  return { read, added, message: read ? `Synced ${read} readings, ${added} new.` : 'Up to date.' };
}

/**
 * Syncs whenever HealthKit says one of the four types changed (also when iOS wakes the
 * app in the background for it). Returns a function that stops listening.
 */
export function watchHealth(onChange: () => void): () => void {
  const subs = ALL_TYPES.map((id) => subscribeToChanges(id, () => onChange()));
  return () => subs.forEach((s) => s.remove());
}
