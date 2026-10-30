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
export type Workout = Schemas['Workout'];
export type SweatSession = Schemas['SweatSession'];
export type NixPreview = Schemas['NixPreview'];
export type ManualSweat = Schemas['ManualSweatIn'];
/**
 * A picked file ready to upload. part is a File on the web, and { uri, name, type } on iPhone,
 * which is what React Native's FormData sends as a file.
 */
export type UploadFile = { name: string; part: Blob; size?: number };
/** The server takes Nix files up to this size (server/app/core/limits.py). A real export is about 160 KB. */
export const MAX_NIX_BYTES = 5 * 1024 * 1024;
/** Where a Nix file is saved: a picked workout, or a new one made from the file's times. */
export type NixTarget = { workoutId: string } | { newWorkout: true };

/**
 * The server's error message. Most errors carry it as text. A 422 from a check on what was sent
 * carries a list, so its messages are joined (without pydantic's "Value error, " prefix).
 */
export function errorDetail(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (typeof d?.msg === 'string' ? d.msg.replace(/^Value error, /, '') : null))
      .filter((m): m is string => !!m);
    if (msgs.length) return msgs.join('. ');
  }
  return `Server replied ${status}`;
}

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
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        // not JSON, the plain message below is used
      }
      throw new ApiError(res.status, errorDetail(body, res.status));
    }
    try {
      return (await res.json()) as T;
    } catch {
      // Something answered, but not with JSON: the address points at some other web page.
      throw new ApiError(res.status, `${base} answered, but it isn't the recovery server. Check the address.`);
    }
  }

  const json = (method: string, body?: unknown): RequestInit => ({
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  /**
   * A Nix upload. The phone's UTC offset goes along, and the server uses it only when it knows neither
   * the person's time zone nor the offset of their latest reading.
   */
  const upload = (file: UploadFile, target?: NixTarget): RequestInit => {
    const form = new FormData();
    form.append('file', file.part, file.name);
    form.append('tz_offset_min', String(-new Date().getTimezoneOffset()));
    if (target && 'workoutId' in target) form.append('workout_id', target.workoutId);
    if (target && 'newWorkout' in target) form.append('new_workout', 'true');
    return { method: 'POST', body: form };
  };

  return {
    health: () => call<Schemas['HealthCheck']>('/health'),
    today: () => call<Today>(`${user}/today`),
    trends: (nights: 14 | 28 | 90) => call<Trends>(`${user}/trends?nights=${nights}`),
    profile: () => call<Profile>(`${user}/profile`),
    settings: () => call<Settings>(`${user}/settings`),
    saveSettings: (changes: SettingsUpdate) => call<Settings>(`${user}/settings`, json('PATCH', changes)),
    updateNow: () => call<ProcessingRun>(`${user}/processing-runs`, json('POST')),
    /** Why this score's "Was this helpful?" for one night. Answering again replaces the earlier answer. */
    saveFeedback: (nightDate: string, helpful: boolean) =>
      call<Schemas['Feedback']>(`${user}/nights/${nightDate}/feedback`, json('PUT', { helpful })),
    /** Sweat per day for the Trends chart, ending yesterday. */
    sweatDaily: (nights: 14 | 28 | 90) => call<Schemas['SweatDaily']>(`${user}/sweat/daily?nights=${nights}`),
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
          let body: unknown = null;
          try {
            body = JSON.parse(xhr.responseText);
          } catch {
            // not JSON, use the status code below
          }
          if (xhr.status >= 200 && xhr.status < 300) resolve(body as ImportJob);
          else reject(new ApiError(xhr.status, errorDetail(body, xhr.status)));
        };
        xhr.onerror = () => reject(new ApiError(0, `Can't reach the server at ${base}. Is it running, and is the address right?`));
        xhr.send(form);
      });
    },
    importStatus: (importId: string) => call<ImportJob>(`${user}/imports/${encodeURIComponent(importId)}`),
    /** This person's latest import, if the server still has it. Empty after a server restart. */
    imports: () => call<ImportJob[]>(`${user}/imports`),
    /** Saves this morning's check-in. Answering again the same morning replaces it. */
    saveCheckin: (body: Schemas['MorningCheckinIn']) =>
      call<Schemas['MorningCheckin']>(`${user}/checkins/morning`, json('POST', body)),
    /** The check-in for a night, or null when there isn't one yet. */
    morningCheckin: async (nightDate: string) => {
      try {
        return await call<Schemas['MorningCheckin']>(`${user}/checkins/morning/${nightDate}`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    /** Workouts that started in the last N days (up to 366), oldest first. */
    workouts: (days = 366) => call<Workout[]>(`${user}/workouts?days=${days}`),
    workout: (id: string) => call<Workout>(`${user}/workouts/${encodeURIComponent(id)}`),
    /** The after-workout check-in. Rating again replaces the earlier answer. */
    rateWorkout: (id: string, body: Schemas['RatingIn']) =>
      call<Workout>(`${user}/workouts/${encodeURIComponent(id)}/rating`, json('PUT', body)),
    /** Adds a workout, or updates it when the same id is sent again. */
    saveWorkout: (body: Schemas['WorkoutIn']) => call<Workout>(`${user}/workouts`, json('POST', body)),
    /** The workout's sweat data, or null when it has none yet. */
    workoutSweat: async (id: string) => {
      try {
        return await call<SweatSession>(`${user}/workouts/${encodeURIComponent(id)}/sweat`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    sweatSessions: (days = 366) => call<SweatSession[]>(`${user}/sweat/sessions?days=${days}`),
    /** What saving this Nix file would do, to the matched workout or the one given. Nothing is stored. */
    previewNix: (file: UploadFile, target?: NixTarget) =>
      call<NixPreview>(`${user}/sweat/nix/preview`, upload(file, target)),
    /** Saves the Nix file, sent again after the preview, so the server never holds unsaved data. */
    saveNix: (file: UploadFile, target: NixTarget) => call<SweatSession>(`${user}/sweat/nix`, upload(file, target)),
    /** Numbers typed in, already in ml, mg and L/h. */
    saveSweatManually: (workoutId: string, body: ManualSweat) =>
      call<SweatSession>(`${user}/workouts/${encodeURIComponent(workoutId)}/sweat`, json('PUT', body)),
    /** Testing only: workouts and sweat data for a demo person who's already loaded. */
    loadDemoSweat: (person: 'sam' | 'alex' | 'jordan') =>
      call<Schemas['DemoSweat']>(`/api/v1/demo-users/${person}/sweat`, json('POST')),
  };
}

export type Api = ReturnType<typeof makeApi>;
