/**
 * Apple Health on iPhone. Metro picks this file on iOS and health.ts everywhere else,
 * so the web version never loads HealthKit.
 *
 * This is the old test screen's logic, kept working until step 5 replaces it with
 * incremental (anchored) sync, sleep stages and background delivery.
 */
import {
  isHealthDataAvailable,
  queryQuantitySamples,
  requestAuthorization,
} from '@kingstinct/react-native-healthkit';

const METRICS = [
  { id: 'HKQuantityTypeIdentifierHeartRate', metric: 'heart_rate' },
  { id: 'HKQuantityTypeIdentifierRestingHeartRate', metric: 'resting_heart_rate' },
  { id: 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN', metric: 'hrv_sdnn' },
] as const;

export const healthAvailable = () => isHealthDataAvailable();

export async function connectHealth(): Promise<void> {
  await requestAuthorization({ toRead: METRICS.map((m) => m.id) });
}

// The phone's UTC offset at that moment. Right unless the person travelled, which step 5 fixes.
const offsetAt = (ms: number) => -new Date(ms).getTimezoneOffset();

/** Reads the last 24 hours and sends it. Returns a short message for the screen. */
export async function sendLastDay(serverUrl: string, userId: string): Promise<string> {
  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - 24 * 60 * 60 * 1000);
  const samples = [];
  for (const m of METRICS) {
    const rows = await queryQuantitySamples(m.id, { limit: 0, filter: { date: { startDate, endDate } } });
    for (const r of rows) {
      const start = new Date(r.startDate).getTime();
      samples.push({
        uuid: r.uuid,
        metric: m.metric,
        value: r.quantity,
        start_ms: start,
        end_ms: new Date(r.endDate).getTime(),
        tz_offset_min: offsetAt(start),
        source: r.sourceRevision?.source?.name ?? null,
      });
    }
  }
  if (samples.length === 0) return 'Nothing to send. Wear the watch for a while, or check permissions.';
  const res = await fetch(`${serverUrl.replace(/\/+$/, '')}/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, samples }),
  });
  if (!res.ok) throw new Error(`Server replied ${res.status}`);
  const body = await res.json();
  return `Sent ${body.received} readings, ${body.new} were new.`;
}
