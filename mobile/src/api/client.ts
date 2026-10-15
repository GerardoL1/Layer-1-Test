/**
 * Talks to the recovery server (server/app/routers/).
 * The types come from the server's own description of its API (src/api/schema.ts, generated).
 * After changing the server, run `python export_openapi.py` in server/ and `npm run api-types` here.
 */
import type { components } from './schema';

type Schemas = components['schemas'];

export type Today = Schemas['Today'];
export type Readiness = Schemas['Readiness'];
export type ReadinessStatus = Readiness['status'];
export type MetricRow = Schemas['MetricRow'];
export type Direction = MetricRow['direction'];
export type SleepBlock = Schemas['SleepBlock'];
export type Trends = Schemas['Trends'];
export type TrendRow = Schemas['TrendRow'];
export type TrendValue = Schemas['TrendValue'];
/** The metrics each Trends row has a value for. */
export type TrendMetric = 'hrv' | 'rhr' | 'sleep' | 'efficiency' | 'fragmentation';
export type Profile = Schemas['Profile'];
export type Settings = Schemas['Settings'];
export type SettingsUpdate = Schemas['SettingsUpdate'];
export type ImportJob = Schemas['ImportJob'];
export type ProcessingRun = Schemas['ProcessingRun'];
export type DemoUser = Schemas['DemoUser'];

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function makeApi(serverUrl: string, userId: string) {
  const base = serverUrl.replace(/\/+$/, '');
  // Everything about this person lives under their user id.
  const user = `/api/v1/users/${encodeURIComponent(userId)}`;

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
    health: () => call<Schemas['HealthCheck']>('/health'),
    today: () => call<Today>(`${user}/today`),
    trends: (nights: 14 | 28 | 90) => call<Trends>(`${user}/trends?nights=${nights}`),
    profile: () => call<Profile>(`${user}/profile`),
    settings: () => call<Settings>(`${user}/settings`),
    saveSettings: (changes: SettingsUpdate) => call<Settings>(`${user}/settings`, json('PATCH', changes)),
    updateNow: () => call<ProcessingRun>(`${user}/processing-runs`, json('POST')),
    loadDemo: (person: 'sam' | 'alex' | 'jordan') =>
      call<DemoUser>(`/api/v1/demo-users/${person}`, json('POST')),
    /** Uploads a Health export and returns the new import. onProgress(0..1) reports how much has been sent. */
    importExport: (file: Blob, name: string, onProgress?: (share: number) => void) => {
      const form = new FormData();
      form.append('file', file, name);
      form.append('since_days', '0');
      // fetch can't report upload progress, XMLHttpRequest can.
      return new Promise<ImportJob>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${base}${user}/imports`);
        xhr.upload.onprogress = (e) => {
          if (onProgress && e.lengthComputable) onProgress(e.loaded / e.total);
        };
        xhr.onload = () => {
          let body: { detail?: unknown } = {};
          try {
            body = JSON.parse(xhr.responseText);
          } catch {
            // not JSON, use the status code below
          }
          if (xhr.status >= 200 && xhr.status < 300) resolve(body as ImportJob);
          else reject(new ApiError(xhr.status, typeof body.detail === 'string' ? body.detail : `Server replied ${xhr.status}`));
        };
        xhr.onerror = () => reject(new ApiError(0, `Can't reach the server at ${base}. Is it running, and is the address right?`));
        xhr.send(form);
      });
    },
    importStatus: (importId: string) => call<ImportJob>(`${user}/imports/${importId}`),
    /** This person's latest import, if the server still has it. Empty after a server restart. */
    imports: () => call<ImportJob[]>(`${user}/imports`),
  };
}

export type Api = ReturnType<typeof makeApi>;
