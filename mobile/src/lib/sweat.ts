/**
 * Sweat numbers and workout lists as the Train screens show them. The server keeps ml, L/h and mg,
 * and the app shows ml/L or oz following Settings → Units.
 * No imports, so scripts/check-convert.js can test it without an iPhone.
 */
export type Units = 'metric' | 'imperial';
export type Shown = { value: string; unit: string };

const ML_PER_OZ = 29.5735;
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December'];
const DASH = '–';
const NOTHING: Shown = { value: DASH, unit: '' };

const thousands = (n: number) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
// The server never sends these, but a dash is better than "NaN L" if something odd gets through.
const bad = (n: number) => !Number.isFinite(n) || n < 0;

/** Fluid: "640 ml" under a litre, "1.4 L" above. In ounces "22 oz", or "2.1 oz" for small amounts. */
export function fluid(ml: number, units: Units): Shown {
  if (bad(ml)) return NOTHING;
  if (units === 'imperial') {
    const oz = ml / ML_PER_OZ;
    // The unit is picked after rounding, so 9.97 oz shows as "10 oz", not "10.0 oz".
    const tenths = Math.round(oz * 10) / 10;
    return { value: tenths < 10 ? tenths.toFixed(1) : thousands(Math.round(oz)), unit: 'oz' };
  }
  if (Math.round(ml) < 1000) return { value: String(Math.round(ml)), unit: 'ml' };
  return { value: (ml / 1000).toFixed(1), unit: 'L' };
}

/** Sweat rate: "1.45 L/h", or "49 oz/h". */
export function rate(lh: number, units: Units): Shown {
  if (bad(lh)) return NOTHING;
  if (units === 'imperial') return { value: String(Math.round((lh * 1000) / ML_PER_OZ)), unit: 'oz/h' };
  return { value: lh.toFixed(2), unit: 'L/h' };
}

/** Sodium is mg in both settings: "1,150 mg". */
export function sodium(mg: number): Shown {
  if (bad(mg)) return NOTHING;
  return { value: thousands(Math.round(mg)), unit: 'mg' };
}

export const joined = (s: Shown) => (s.unit ? `${s.value} ${s.unit}` : s.value);

/**
 * The rehydrate amount, rounded the way people pour: "around 2 L", "around 600 ml", "around 68 oz".
 * Null when there's nothing sensible to say.
 */
export function about(ml: number, units: Units): string | null {
  if (bad(ml) || ml === 0) return null;
  if (units === 'imperial') return `around ${Math.max(1, Math.round(ml / ML_PER_OZ))} oz`;
  const hundreds = Math.max(100, Math.round(ml / 100) * 100);
  // Rounded first, so 960 ml reads "around 1 L" rather than "around 1000 ml".
  if (hundreds >= 1000) return `around ${Math.round(ml / 500) / 2} L`;
  return `around ${hundreds} ml`;
}

/** "35 min", "1 h 14 min", "2 h". */
export function duration(min: number): string {
  if (bad(min)) return DASH;
  const m = Math.round(min);
  if (m < 60) return `${m} min`;
  return m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} h`;
}

/** What a screen reader says for a duration: "1 hour 14 minutes". */
export function durationWords(min: number): string {
  if (bad(min)) return 'not known';
  const m = Math.round(min);
  const word = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`;
  const hours = Math.floor(m / 60);
  const rest = m % 60;
  if (!hours) return word(rest, 'minute');
  return rest ? `${word(hours, 'hour')} ${word(rest, 'minute')}` : word(hours, 'hour');
}

/** Where a workout came from, as the workout rows say it. */
export function sourceText(source: string): string {
  if (source === 'apple_health') return 'Apple Watch';
  if (source === 'patch') return 'Started in the app';
  return 'Added in the app';
}

/** "2026-09-30T18:05" -> a date at local midnight and the minutes into the day, or null if it isn't one. */
function parts(iso: string) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(iso ?? '');
  if (!m) return null;
  const date = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return { date, h: Number(m[4] ?? 0), min: Number(m[5] ?? 0) };
}

function clock(h: number, min: number): string {
  return `${h % 12 === 0 ? 12 : h % 12}:${String(min).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

const dayText = (d: Date) => `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;

/** "Tue 30 Sep · 7:05 AM" (a label style shows it in capitals). */
export function startLabel(startLocal: string): string {
  const p = parts(startLocal);
  return p ? `${dayText(p.date)} · ${clock(p.h, p.min)}` : DASH;
}

/**
 * "Mon 29 Sep · 6:10–7:08 PM". Both halves in full when AM and PM differ, the end day too when the
 * workout crosses midnight, and just the start when it has no length.
 */
export function spanLabel(startLocal: string, endLocal: string): string {
  const a = parts(startLocal);
  const b = parts(endLocal);
  if (!a || !b) return startLabel(startLocal);
  const day = dayText(a.date);
  if (a.date.getTime() !== b.date.getTime()) {
    return `${day} · ${clock(a.h, a.min)} – ${dayText(b.date)} ${clock(b.h, b.min)}`;
  }
  if (a.h === b.h && a.min === b.min) return `${day} · ${clock(a.h, a.min)}`;
  const start = a.h < 12 === b.h < 12 ? clock(a.h, a.min).slice(0, -3) : clock(a.h, a.min);
  return `${day} · ${start}–${clock(b.h, b.min)}`;
}

type Dated = { start_local: string };

/** The same calendar day `days` earlier. Calendar maths, so a 23 or 25 hour day around a clock change is fine. */
function daysBefore(d: Date, days: number): Date {
  const out = new Date(d);
  out.setDate(d.getDate() - days);
  return out;
}

/** Workouts that started in the last 7 calendar days up to today, newest first (Train's "Last 7 days"). */
export function lastSevenDays<T extends Dated>(workouts: T[], nowLocal: string): T[] {
  const now = parts(nowLocal);
  if (!now) return [];
  const from = daysBefore(now.date, 6).getTime();
  return newestFirst(workouts.filter((w) => {
    const p = parts(w.start_local);
    return !!p && p.date.getTime() >= from && p.date.getTime() <= now.date.getTime();
  }));
}

function newestFirst<T extends Dated>(workouts: T[]): T[] {
  return [...workouts].sort((a, b) => b.start_local.localeCompare(a.start_local));
}

/**
 * All workouts in sections: Upcoming (after today), This week and Last week (weeks start on Monday),
 * then one per month.
 */
export function sections<T extends Dated>(workouts: T[], nowLocal: string): { title: string; items: T[] }[] {
  const now = parts(nowLocal);
  const today = now ? now.date : new Date();
  const monday = daysBefore(today, (today.getDay() + 6) % 7);
  const lastMonday = daysBefore(monday, 7);
  const out: { title: string; items: T[] }[] = [];
  for (const w of newestFirst(workouts)) {
    const p = parts(w.start_local);
    let title = 'Unknown date';
    if (p) {
      const d = p.date;
      const sameYear = d.getFullYear() === today.getFullYear();
      title = d > today ? 'Upcoming' : d >= monday ? 'This week' : d >= lastMonday ? 'Last week'
        : `${MONTH_NAMES[d.getMonth()]}${sameYear ? '' : ` ${d.getFullYear()}`}`;
    }
    const group = out.find((g) => g.title === title);
    if (group) group.items.push(w);
    else out.push({ title, items: [w] });
  }
  return out;
}

type SessionNumbers = {
  sweat_detected: boolean;
  fluid_loss_ml: number;
  sweat_rate_l_h: number | null;
  sodium_mg: number | null;
};
export type Stat = { label: string; shown: Shown | null; tone: 'sweat' | 'muted' };

/**
 * The numbers a workout's Sweat section shows. When Nix picked up no sweat, its numbers are breathing
 * loss only, so they're labelled that way, muted, and sodium (never measured) is left out.
 */
export function sessionStats(s: SessionNumbers, units: Units): Stat[] {
  const r = s.sweat_rate_l_h === null ? null : rate(s.sweat_rate_l_h, units);
  if (!s.sweat_detected) {
    return [
      { label: 'Breathing loss', shown: fluid(s.fluid_loss_ml, units), tone: 'muted' },
      { label: 'Breathing rate', shown: r, tone: 'muted' },
    ];
  }
  return [
    { label: 'Fluid lost', shown: fluid(s.fluid_loss_ml, units), tone: 'sweat' },
    { label: 'Sweat rate', shown: r, tone: 'sweat' },
    { label: 'Sodium lost', shown: s.sodium_mg === null ? null : sodium(s.sodium_mg), tone: 'sweat' },
  ];
}

export type Suggestion = { title: string; text: string; effort: string };

/**
 * Today's suggestion on Train. A placeholder from the readiness status alone, until Layer 2's muscle data
 * and the team's rules exist. Null when there's no score to go on.
 */
export function suggestion(status: string | null | undefined): Suggestion | null {
  if (status === 'low') {
    return { title: 'Keep it easy today.', effort: 'Easy',
      text: 'Your readiness is low. Light movement, mobility or rest will help you recover.' };
  }
  if (status === 'moderate') {
    return { title: 'Train, but keep it moderate.', effort: 'Easy to moderate',
      text: 'Your readiness is in the middle. A normal session is fine, just skip your hardest sets.' };
  }
  if (status === 'ready') {
    return { title: 'Good day to train hard.', effort: 'Hard',
      text: 'Your readiness is high. If a hard session is on your plan, today suits it.' };
  }
  return null;
}
