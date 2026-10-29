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
  return `${h % 12 === 0 ? 12 : h % 12}:${String(min).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
}

const dayText = (d: Date) => `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;

/** "Tue 30 Sep · 7:05 am". */
export function startLabel(startLocal: string): string {
  const p = parts(startLocal);
  return p ? `${dayText(p.date)} · ${clock(p.h, p.min)}` : DASH;
}

/**
 * "Mon 29 Sep · 6:10–7:08 pm". Both halves in full when am and pm differ, the end day too when the
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

/** Workouts whose sweat session picked up real sweat. Breathing-only sessions don't earn the SWEAT tag. */
export function sweatWorkoutIds(sessions: { workout_id: string | null; sweat_detected: boolean }[]): Set<string> {
  return new Set(sessions.flatMap((s) => (s.sweat_detected && s.workout_id ? [s.workout_id] : [])));
}

const CHECK_LABELS: Record<string, string> = { 'Fluid lost': 'Sweat loss', 'Sodium lost': 'Sodium loss' };

/** Check your import names the numbers the way Figma does, which differs from the workout screen. */
export const checkLabel = (label: string) => CHECK_LABELS[label] ?? label;

// ---------------------------------------------------------------- typed-in numbers and the import notes

export type AmountKind = 'fluid' | 'sodium' | 'rate';

/**
 * What the server accepts (server/app/schemas/sweat.py), in each unit people can type. The ounce limits are
 * rounded inwards, so a typed amount never lands outside the server's range after converting.
 */
const AMOUNT_LIMITS = {
  fluid: { metric: { lo: 1, hi: 30000, unit: 'ml', toStored: 1 }, imperial: { lo: 0.1, hi: 1014, unit: 'oz', toStored: ML_PER_OZ } },
  sodium: { metric: { lo: 1, hi: 100000, unit: 'mg', toStored: 1 }, imperial: { lo: 1, hi: 100000, unit: 'mg', toStored: 1 } },
  rate: {
    metric: { lo: 0.01, hi: 10, unit: 'L/h', toStored: 1 },
    imperial: { lo: 1, hi: 338, unit: 'oz/h', toStored: ML_PER_OZ / 1000 },
  },
} as const;
const AMOUNT_NAMES = { fluid: 'sweat loss', sodium: 'sodium loss', rate: 'sweat rate' };
const STORED_PLACES = { fluid: 1, sodium: 1, rate: 4 };

/** The unit a field shows next to its box. */
export function amountUnit(kind: AmountKind, units: Units): string {
  return AMOUNT_LIMITS[kind][units].unit;
}

/**
 * Typed text to the stored unit (ml, mg or L/h). Sweat loss is required, the others can be left empty.
 * Accepts "1,150" thousands and "1,5" decimals, like the Weight box.
 */
export function parseAmount(text: string, kind: AmountKind, units: Units): { value: number | null } | { error: string } {
  const t = text.trim();
  const { lo, hi, unit, toStored } = AMOUNT_LIMITS[kind][units];
  const range = `between ${thousands(lo)} and ${thousands(hi)} ${unit}`;
  if (!t) return kind === 'fluid' ? { error: 'Type how much sweat you lost.' } : { value: null };
  // "1,500" is thousands. "0,500" can only be a decimal comma (0.5), so a leading zero rules thousands out.
  const plain = /^[1-9]\d{0,2}(,\d{3})+(\.\d+)?$/.test(t) ? t.replace(/,/g, '') : t.replace(',', '.');
  const n = /^(\d+\.?\d*|\.\d+)$/.test(plain) ? Number(plain) : NaN;
  if (!(n >= lo && n <= hi)) {
    return { error: `Type a ${AMOUNT_NAMES[kind]} ${range}${kind === 'fluid' ? '' : ', or leave it empty'}.` };
  }
  const f = 10 ** STORED_PLACES[kind];
  return { value: Math.round(n * toStored * f) / f };
}

/** What a box shows for a number already saved (ml, mg or L/h), in the person's units. Empty when there's none. */
export function amountInput(value: number | null, kind: AmountKind, units: Units): string {
  if (value === null || bad(value)) return '';
  if (kind === 'fluid') return units === 'imperial' ? String(Math.round((value / ML_PER_OZ) * 10) / 10) : String(Math.round(value));
  if (kind === 'rate') return units === 'imperial' ? String(Math.round((value * 1000) / ML_PER_OZ)) : String(Number(value.toFixed(2)));
  return String(Math.round(value));
}

/**
 * Like parseAmount, but a box still showing the saved number gives back that exact number.
 * Otherwise 640 ml shown as 21.6 oz would quietly save as 638.8 ml.
 */
export function typedValue(text: string, kind: AmountKind, units: Units, saved: number | null) {
  if (saved !== null && text.trim() && text.trim() === amountInput(saved, kind, units)) return { value: saved };
  return parseAmount(text, kind, units);
}

/** An example in the box, sized for the unit (1.2 makes sense in L/h, not in oz/h). */
export function amountHint(kind: AmountKind, units: Units): string {
  const examples = { fluid: { metric: '900', imperial: '30' }, sodium: { metric: '640', imperial: '640' },
    rate: { metric: '1.2', imperial: '40' } };
  return `e.g. ${examples[kind][units]}`;
}

/** Saving would be refused (409), so Save stays off and the note says why. */
export function isRefused(existing: string): boolean {
  return existing === 'keeps_more_precise' || existing === 'keeps_sweat_data';
}

/** The same file is already saved on another workout, and saving here takes it off that one. */
export function movesNote(otherWorkout: string): string {
  return `This file is saved on ${otherWorkout}. Saving here moves it off that workout.`;
}

/** What saving would do to sweat data the workout already has, as the preview's "existing" says. */
export function existingNote(existing: string): string | null {
  if (existing === 'keeps_sweat_data') {
    return 'This workout already has sweat data, and Nix picked up no sweat in this file, so saving won’t change it.';
  }
  if (existing === 'same') return 'You’ve already saved this file. Saving it again changes nothing.';
  if (existing === 'replaces') return 'Replaces the sweat data this workout already has.';
  if (existing === 'replaces_less_precise') return 'Replaces your earlier sweat data with more precise numbers.';
  if (existing === 'keeps_more_precise') {
    return 'This workout already has more precise sweat data, so saving this file won’t change it.';
  }
  return null;
}

/** When the import was opened from one workout but the file's times are from another moment. */
export function notThisWorkout(startLocal: string): string {
  const p = parts(startLocal);
  const when = p ? `${dayText(p.date)} at ${clock(p.h, p.min)}` : 'another time';
  return `This file is from ${when}, not this workout.`;
}

type Extras = {
  electrolytes_mg: number | null;
  sodium_rate_mg_h: number | null;
  sweat_composition_mg_l: number | null;
  nix_index: number | null;
};

/** The numbers besides the main three, as Figma's "Also in the file" rows. Missing ones are left out. */
export function fileExtras(s: Extras): { label: string; value: string }[] {
  const row = (label: string, x: number | null, unit: string) =>
    x === null ? [] : [{ label, value: `${thousands(Math.round(x))}${unit ? ` ${unit}` : ''}` }];
  return [
    ...row('Electrolyte loss', s.electrolytes_mg, 'mg'),
    ...row('Sodium rate', s.sodium_rate_mg_h, 'mg/h'),
    ...row('Sweat composition', s.sweat_composition_mg_l, 'mg/L'),
    ...row('Nix index', s.nix_index, ''),
  ];
}

const SENTENCE_NAMES: Record<string, string> = { 'Electrolyte loss': 'electrolytes' };

/** The same numbers as one line for the iPhone: "Also in the file: electrolytes 860 mg, Nix index 74." */
export function alsoSaved(s: Extras): string | null {
  const bits = fileExtras(s).map((r) => {
    const name = SENTENCE_NAMES[r.label] ?? (r.label === 'Nix index' ? r.label : r.label.toLowerCase());
    return `${name} ${r.value}`;
  });
  return bits.length ? `Also in the file: ${bits.join(', ')}.` : null;
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
