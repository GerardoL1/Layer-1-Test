/**
 * Talks to the recovery server (server/api.py). Types mirror its JSON responses.
 */

export type ReadinessStatus = 'low' | 'moderate' | 'ready' | 'building_baseline' | 'no_data';

export type Readiness = { score: number | null; status: ReadinessStatus; z_count: number; placeholder: boolean };

export type Direction = 'better' | 'usual' | 'worse' | null;

export type MetricRow = {
  key: string;
  label: string;
  unit: string;
  value: number | null;
  z: number | null;
  usual_low: number | null;
  usual_high: number | null;
  usual_mean?: number | null;
  direction: Direction;
  placeholder: boolean;
};

export type SleepBlock = {
  onset: string | null;
  wake: string | null;
  total_min: number | null;
  deep_min: number | null;
  core_min: number | null;
  rem_min: number | null;
  unspecified_min: number | null;
  awake_min: number | null;
  in_bed_min: number | null;
  efficiency_pct: number | null;
};

export type Today = {
  user_id: string;
  now_local: string;
  update_time: string;
  next_update: string;
  updated_at: string | null;
  can_update_now: boolean;
  night_date: string | null;
  is_last_night: boolean;
  message: string | null;
  readiness: Readiness | null;
  metrics: MetricRow[];
  sleep: SleepBlock | null;
  quality_notes: string | null;
  cutoffs: { low_below: number; ready_from: number; placeholder: boolean };
  verdict?: string | null;
  reason?: string | null;
};

export type TrendValue = { value: number | null; z: number | null; usual_low: number | null; usual_high: number | null };

export type TrendRow = {
  night_date: string;
  readiness: Readiness;
  usable_sleep: boolean;
  quality_notes: string | null;
  deep_min: number | null;
  core_min: number | null;
  rem_min: number | null;
  unspecified_min: number | null;
  [metric: string]: TrendValue | unknown;
};

export type Trends = {
  user_id: string;
  nights: 14 | 28 | 90;
  cutoffs: { low_below: number; ready_from: number };
  rows: TrendRow[];
  summaries?: Record<string, string | null>;
};

export type Settings = {
  timezone: string | null;
  update_time: string;
  age: number | null;
  training: string | null;
  training_days: number[];
  units: 'metric' | 'imperial';
};

export type Profile = {
  user_id: string;
  settings: Settings;
  nights_total: number;
  nights_usable: number;
  first_night: string | null;
  last_night: string | null;
  baseline_window_nights: number;
  baseline_min_nights: number;
  usual_ranges: { key: string; label: string; unit: string; usual_low: number | null; usual_high: number | null;
    baseline_nights: number | null; placeholder: boolean }[];
  sources: string[];
  last_update_local: string | null;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function makeApi(serverUrl: string, userId: string) {
  const base = serverUrl.replace(/\/+$/, '');
  const q = (extra: Record<string, string | number> = {}) =>
    '?' + new URLSearchParams({ user_id: userId, ...Object.fromEntries(
      Object.entries(extra).map(([k, v]) => [k, String(v)])) }).toString();

  async function call<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await fetch(base + path, init);
    } catch {
      throw new ApiError(0, `Can't reach the server at ${base}. Is it running, and is the address right?`);
    }
    if (!res.ok) {
      let detail = `Server replied ${res.status}`;
      try {
        const body = await res.json();
        if (typeof body.detail === 'string') detail = body.detail;
      } catch {
        // not JSON, keep the plain message
      }
      throw new ApiError(res.status, detail);
    }
    return res.json() as Promise<T>;
  }

  const json = (method: string, body?: unknown): RequestInit => ({
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  return {
    health: () => call<{ ok: boolean }>('/health'),
    today: () => call<Today>('/api/today' + q()),
    trends: (nights: 14 | 28 | 90) => call<Trends>('/api/trends' + q({ nights })),
    profile: () => call<Profile>('/api/profile' + q()),
    settings: () => call<Settings>('/api/settings' + q()),
    saveSettings: (changes: Partial<Settings>) => call<Settings>('/api/settings' + q(), json('PUT', changes)),
    updateNow: () => call<{ processed: boolean; new_nights: string[]; message: string }>(
      '/api/update-now' + q(), json('POST')),
    loadDemo: (person: 'sam' | 'alex' | 'jordan') =>
      call<{ user_id: string; clock_local: string }>(`/api/demo/${person}`, json('POST')),
    importExport: (file: Blob, name: string) => {
      const form = new FormData();
      form.append('file', file, name);
      form.append('user_id', userId);
      form.append('since_days', '0');
      return call<{ started: boolean }>('/api/import', { method: 'POST', body: form });
    },
    importStatus: () => call<{ state: string; counts?: Record<string, number>; error?: string | null }>(
      '/api/import/status'),
  };
}

export type Api = ReturnType<typeof makeApi>;
