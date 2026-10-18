/**
 * What screen readers hear for each chart. A chart is a picture, so without this a blind user
 * only gets its title. These say what the picture shows: latest value, range, how often you
 * were inside your usual, and for readiness how many nights were Ready, Moderate or Low.
 */
import type { TrendMetric } from '../api/client';
import { monthDay } from '../lib/format';
import type { HistoryBar, SleepNight, TrendPoint } from './Charts';

export const TREND_UNITS: Partial<Record<TrendMetric, string>> = { hrv: 'ms', rhr: 'bpm', efficiency: '%' };

function amount(v: number, unit?: string): string {
  const n = Math.round(v);
  if (!unit) return `${n}`;
  return unit === '%' ? `${n}%` : `${n} ${unit}`;
}

export function describeTrend(label: string, points: TrendPoint[], unit?: string): string {
  const withValue = points.filter((p): p is TrendPoint & { value: number } => p.value !== null);
  if (withValue.length === 0) return `${label}. No nights with data yet.`;
  const last = withValue[withValue.length - 1];
  const values = withValue.map((p) => p.value);
  const parts = [
    `${label}.`,
    `Latest ${amount(last.value, unit)} on ${monthDay(last.date)}.`,
    `Lowest ${amount(Math.min(...values), unit)}, highest ${amount(Math.max(...values), unit)}, `
      + `over ${withValue.length} of ${points.length} nights.`,
  ];
  const judged = withValue.filter((p) => p.usualLow !== null && p.usualHigh !== null);
  if (judged.length) {
    const inside = judged.filter((p) => p.value >= p.usualLow! && p.value <= p.usualHigh!).length;
    parts.push(`Inside your usual range on ${inside} of ${judged.length} nights.`);
  }
  return parts.join(' ');
}

export function describeHistory(bars: HistoryBar[], words: Record<string, string>): string {
  const scored = bars.filter((b) => b.score !== null);
  const parts = [`Readiness for the last ${bars.length} nights.`];
  if (scored.length === 0) return `${parts[0]} No scores yet.`;
  const counts = new Map<string, number>();
  scored.forEach((b) => counts.set(b.status, (counts.get(b.status) ?? 0) + 1));
  // Ready, Moderate and Low first since those are what people look for, then anything else.
  const order = ['ready', 'moderate', 'low', ...[...counts.keys()].filter((k) => !['ready', 'moderate', 'low'].includes(k))];
  const listed = order.filter((k) => counts.has(k)).map((k) => `${counts.get(k)} ${words[k] ?? k}`);
  parts.push(`${listed.join(', ')}.`);
  const last = scored[scored.length - 1];
  parts.push(`Latest ${Math.round(last.score!)} on ${monthDay(last.date)}, ${words[last.status] ?? last.status}.`);
  return parts.join(' ');
}

/** 459 -> "7 hours 39 minutes". Read aloud, "7:39" sounds like a time of day. */
function spoken(min: number): string {
  const total = Math.round(min);
  const h = Math.floor(total / 60);
  const m = total % 60;
  const hours = h ? `${h} ${h === 1 ? 'hour' : 'hours'}` : '';
  const minutes = m || !h ? `${m} ${m === 1 ? 'minute' : 'minutes'}` : '';
  return [hours, minutes].filter(Boolean).join(' ');
}

export function describeSleep(nights: SleepNight[]): string {
  const total = (n: SleepNight) => (n.deep ?? 0) + (n.core ?? 0) + (n.rem ?? 0) + (n.other ?? 0);
  const slept = nights.filter((n) => total(n) > 0);
  const head = `Sleep stages for the last ${nights.length} nights.`;
  if (slept.length === 0) return `${head} No sleep recorded.`;
  const avg = (pick: (n: SleepNight) => number) => slept.reduce((sum, n) => sum + pick(n), 0) / slept.length;
  const last = slept[slept.length - 1];
  return [
    head,
    `Average ${spoken(avg(total))} asleep on ${slept.length} nights: `
      + `deep ${spoken(avg((n) => n.deep ?? 0))}, core ${spoken(avg((n) => n.core ?? 0))}, `
      + `REM ${spoken(avg((n) => n.rem ?? 0))}.`,
    `Latest ${spoken(total(last))} on ${monthDay(last.date)}.`,
  ].join(' ');
}
