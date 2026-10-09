/**
 * Turns HealthKit samples into what the server's POST /upload expects.
 * No HealthKit imports here, so this file also runs (and is tested) on a computer.
 */

export type UploadSample = {
  uuid: string;
  metric: 'heart_rate' | 'resting_heart_rate' | 'hrv_sdnn';
  value: number;
  start_ms: number;
  end_ms: number;
  tz_offset_min: number;
  source: string | null;
};

export type UploadStage = {
  uuid: string;
  stage: 'in_bed' | 'asleep_unspecified' | 'awake' | 'core' | 'deep' | 'rem';
  start_ms: number;
  end_ms: number;
  start_tz_min: number;
  end_tz_min: number;
  source: string | null;
};

// HealthKit's sleep values (HKCategoryValueSleepAnalysis) to the server's stage names.
export const SLEEP_STAGE: Record<number, UploadStage['stage']> = {
  0: 'in_bed',
  1: 'asleep_unspecified',
  2: 'awake',
  3: 'core',
  4: 'deep',
  5: 'rem',
};

/** Minimal shape of a HealthKit sample, the parts we use. */
export type HKLike = {
  uuid: string;
  startDate: Date | string;
  endDate: Date | string;
  metadata?: { HKTimeZone?: unknown } | Record<string, unknown>;
  sourceRevision?: { source?: { name?: string } };
};

const ms = (d: Date | string) => (d instanceof Date ? d.getTime() : new Date(d).getTime());

/**
 * Minutes ahead of UTC in an IANA time zone (e.g. "America/Chicago") at a moment.
 * Returns null if the zone isn't known, so the caller can fall back.
 */
export function offsetInZone(zone: string, atMs: number): number | null {
  try {
    const f = new Intl.DateTimeFormat('en-US', {
      timeZone: zone, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
    const p: Record<string, number> = {};
    for (const part of f.formatToParts(new Date(atMs))) {
      if (part.type !== 'literal') p[part.type] = Number(part.value);
    }
    // The wall-clock time there, read as if it were UTC, minus the real UTC time.
    const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
    return Math.round((asUtc - Math.floor(atMs / 1000) * 1000) / 60000);
  } catch {
    return null;
  }
}

/** The phone's own UTC offset at a moment. Right unless the person was travelling. */
export const deviceOffset = (atMs: number) => -new Date(atMs).getTimezoneOffset();

/**
 * Best guess of the UTC offset when a sample was recorded. Apple Watch sleep samples
 * usually carry the time zone they were recorded in (HKTimeZone), which stays right
 * after travel. Otherwise use the phone's offset at that moment.
 */
export function offsetFor(sample: HKLike, atMs: number): number {
  const zone = (sample.metadata as { HKTimeZone?: unknown } | undefined)?.HKTimeZone;
  if (typeof zone === 'string' && zone) {
    const off = offsetInZone(zone, atMs);
    if (off !== null) return off;
  }
  return deviceOffset(atMs);
}

const sourceName = (s: HKLike) => s.sourceRevision?.source?.name ?? null;

export function toUploadSample(metric: UploadSample['metric'], s: HKLike & { quantity: number }): UploadSample {
  const start = ms(s.startDate);
  return {
    uuid: s.uuid,
    metric,
    value: s.quantity,
    start_ms: start,
    end_ms: ms(s.endDate),
    tz_offset_min: offsetFor(s, start),
    source: sourceName(s),
  };
}

/** Returns null for sleep values the server doesn't know (future iOS categories). */
export function toUploadStage(s: HKLike & { value: number }): UploadStage | null {
  const stage = SLEEP_STAGE[s.value];
  if (!stage) return null;
  const start = ms(s.startDate);
  const end = ms(s.endDate);
  return {
    uuid: s.uuid,
    stage,
    start_ms: start,
    end_ms: end,
    start_tz_min: offsetFor(s, start),
    end_tz_min: offsetFor(s, end),
    source: sourceName(s),
  };
}

/** Splits a list into pieces of at most size, so one upload never gets too big. */
export function chunks<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}
