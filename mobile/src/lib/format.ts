/**
 * Turning server numbers into the text the screens show.
 */
import { MetricRow } from '../api/client';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];   // server uses 0 = Monday

/** Dates come as "2026-10-01" or "2026-10-01T08:30". Read them as local wall-clock time. */
function parts(iso: string) {
  const [d, t = '00:00'] = iso.split('T');
  const [y, m, day] = d.split('-').map(Number);
  const [h, min] = t.split(':').map(Number);
  return { date: new Date(y, m - 1, day), h, min };
}

/** "Wed 1 Oct" */
export function dayLabel(iso: string): string {
  const { date } = parts(iso);
  return `${DAYS[date.getDay()]} ${date.getDate()} ${MONTHS[date.getMonth()]}`;
}

/** "Sep 18" */
export function monthDay(iso: string): string {
  const { date } = parts(iso);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

/** "Aug 1, 2026" */
export function longDate(iso: string): string {
  const { date } = parts(iso);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}, ${date.getFullYear()}`;
}

/** "07:30" or "2026-10-01T07:12" -> "7:30 am" */
export function clock(value: string): string {
  const t = value.includes('T') ? value.split('T')[1] : value;
  const [h, m] = t.split(':').map(Number);
  return `${h % 12 === 0 ? 12 : h % 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
}

/** Minutes -> "6:03" (hours:minutes). */
export function hoursMinutes(min: number | null | undefined): string {
  if (min === null || min === undefined) return '–';
  const total = Math.round(min);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

export function num(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined ? '–' : v.toFixed(digits);
}

/** What a Last night row shows: value, unit and the change against your usual. */
export function metricDisplay(m: MetricRow): { value: string; unit: string; delta: string | null } {
  const mean = m.usual_mean ?? null;
  const diff = m.value !== null && mean !== null ? m.value - mean : null;
  const sign = (n: number) => (n > 0 ? '+' : n < 0 ? '−' : '');
  switch (m.key) {
    case 'hrv':
      return { value: num(m.value), unit: 'ms',
        delta: diff === null || !mean ? null : `${sign(diff)}${Math.abs(Math.round((diff / mean) * 100))}%` };
    case 'rhr':
      return { value: num(m.value), unit: 'bpm',
        delta: diff === null ? null : `${sign(Math.round(diff))}${Math.abs(Math.round(diff))} bpm` };
    case 'sleep':
      return { value: hoursMinutes(m.value), unit: 'h',
        delta: diff === null ? null : `${sign(Math.round(diff))}${Math.abs(Math.round(diff))} min` };
    case 'efficiency':
      return { value: num(m.value), unit: '%',
        delta: diff === null ? null : `${sign(Math.round(diff))}${Math.abs(Math.round(diff))} pts` };
    case 'awakenings':
      // No usual range for the count, so show the word instead of a number.
      return { value: num(m.value), unit: '',
        delta: m.direction === null ? null : m.direction === 'usual' ? 'Usual' : m.direction === 'worse' ? 'More' : 'Fewer' };
    default:
      return { value: num(m.value, 1), unit: m.unit, delta: null };
  }
}

/** "48–58 ms" style usual range, or null when there's no baseline yet. */
export function rangeText(low: number | null, high: number | null, key: string): string | null {
  if (low === null || high === null) return null;
  if (key === 'sleep') return `${hoursMinutes(low)}–${hoursMinutes(high)} h`;
  if (key === 'fragmentation') return `${low.toFixed(1)}–${high.toFixed(1)} an hour`;
  const unit = key === 'hrv' ? ' ms' : key === 'rhr' ? ' bpm' : key === 'efficiency' ? '%' : '';
  return `${Math.round(low)}–${Math.round(high)}${unit}`;
}

/** "demo-alex" -> "Alex (demo)", "tester1" -> "Tester1" */
export function displayName(userId: string): string {
  const demo = userId.startsWith('demo-');
  const name = demo ? userId.slice(5) : userId;
  return name.charAt(0).toUpperCase() + name.slice(1) + (demo ? ' (demo)' : '');
}
