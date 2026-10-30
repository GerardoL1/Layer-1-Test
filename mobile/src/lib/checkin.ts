/**
 * The morning check-in (Figma "Check-in v2"): its questions, and turning the answers into what the server takes
 * (server/app/schemas/checkins.py). Type imports only, so scripts/check-convert.js can test it without an iPhone.
 */
import type { components } from '../api/schema';

type Schemas = components['schemas'];
export type MorningAnswers = Schemas['MorningAnswers'];
export type MuscleGroup = NonNullable<MorningAnswers['sore_muscles']>[number];
export type Unusual = NonNullable<MorningAnswers['unusual']>[number];
export type Rehydrated = NonNullable<MorningAnswers['rehydrated']>;
export type ScaleKey = 'ready_to_train' | 'sleep_quality' | 'fatigue' | 'energy' | 'stress' | 'motivation'
  | 'hydration' | 'soreness';

/** low and high are the words under 1 and 10. 10 is always the good end. */
export type ScaleQuestion = { key: ScaleKey; question: string; low: string; high: string };

export const SCALES: ScaleQuestion[] = [
  { key: 'ready_to_train', question: 'How ready do you feel to train hard today?', low: 'Not at all', high: 'Completely ready' },
  { key: 'sleep_quality', question: 'How well did you sleep?', low: 'Very poorly', high: 'Extremely well' },
  { key: 'fatigue', question: 'How physically fatigued do you feel?', low: 'Exhausted', high: 'Not fatigued' },
  { key: 'energy', question: 'How much energy do you have?', low: 'No energy', high: 'Full of energy' },
  { key: 'stress', question: 'How stressed do you feel?', low: 'Very stressed', high: 'Not stressed' },
  { key: 'motivation', question: 'How motivated are you to work out?', low: 'Not at all', high: 'Very motivated' },
  { key: 'hydration', question: 'How hydrated do you feel?', low: 'Dehydrated', high: 'Fully hydrated' },
  { key: 'soreness', question: 'How sore are your muscles?', low: 'Very sore', high: 'Not sore at all' },
];

/** Which scales each iPhone step asks. The muscles step adds the body map and the chips. */
export const STEP_SCALES: ScaleKey[][] = [
  ['ready_to_train', 'sleep_quality', 'fatigue'],
  ['energy', 'stress', 'motivation', 'hydration'],
  ['soreness'],
];

/** The 14 body map groups, in the server's order, front then back. */
export const MUSCLES: { value: MuscleGroup; label: string }[] = [
  { value: 'shoulders', label: 'Shoulders' },
  { value: 'chest', label: 'Chest' },
  { value: 'biceps', label: 'Biceps' },
  { value: 'forearms', label: 'Forearms' },
  { value: 'abs', label: 'Abs' },
  { value: 'quads', label: 'Quads' },
  { value: 'shins', label: 'Shins' },
  { value: 'traps', label: 'Traps' },
  { value: 'lats', label: 'Lats' },
  { value: 'triceps', label: 'Triceps' },
  { value: 'lower_back', label: 'Lower back' },
  { value: 'glutes', label: 'Glutes' },
  { value: 'hamstrings', label: 'Hamstrings' },
  { value: 'calves', label: 'Calves' },
];

export const UNUSUAL: { value: Unusual | 'none'; label: string }[] = [
  { value: 'alcohol', label: 'Alcohol' },
  { value: 'feeling_sick', label: 'Feeling sick' },
  { value: 'late_caffeine', label: 'Late caffeine' },
  { value: 'travel', label: 'Travel' },
  { value: 'poor_diet', label: 'Poor diet' },
  { value: 'none', label: 'None' },
];

export const REHYDRATED: { value: Rehydrated; label: string }[] = [
  { value: 'not_really', label: 'Not really' },
  { value: 'somewhat', label: 'Somewhat' },
  { value: 'fully', label: 'Fully' },
];

/** What's picked so far. null means not answered, and [] for unusual means "None". */
export type CheckinForm = {
  scales: Partial<Record<ScaleKey, number>>;
  sore: MuscleGroup[];
  unusual: Unusual[] | null;
  rehydrated: Rehydrated | null;
};

export const EMPTY_FORM: CheckinForm = { scales: {}, sore: [], unusual: null, rehydrated: null };

/** Tapping a muscle adds it, tapping it again takes it off. Kept in the server's order. */
export function toggleMuscle(sore: MuscleGroup[], m: MuscleGroup): MuscleGroup[] {
  const next = sore.includes(m) ? sore.filter((x) => x !== m) : [...sore, m];
  return MUSCLES.map((g) => g.value).filter((v) => next.includes(v));
}

/** "None" clears the rest, any other pick clears "None". Tapping a picked one again takes it off. */
export function toggleUnusual(cur: Unusual[] | null, v: Unusual | 'none'): Unusual[] | null {
  if (v === 'none') return cur && cur.length === 0 ? null : [];
  const list = cur ?? [];
  const next = list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
  return next.length ? next : null;
}

const pad = (n: number) => String(n).padStart(2, '0');
const dateValue = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** The night this morning's answers describe: yesterday on the phone's calendar, like the server works it out. */
export function nightFor(now: Date): string {
  return dateValue(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
}

/** Yesterday's latest workout, for "Did you rehydrate after yesterday's run?". null when there wasn't one. */
export function yesterdaysWorkout<W extends { start_local: string }>(workouts: W[], now: Date): W | null {
  const night = nightFor(now);
  const found = workouts.filter((w) => w.start_local.slice(0, 10) === night);
  return found.length ? found[found.length - 1] : null;
}

/** The answers to send. Only "How ready" is required, so it's null until that's picked. */
export function checkinBody(form: CheckinForm, now: Date, askRehydrate: boolean): Schemas['MorningCheckinIn'] | null {
  const ready = form.scales.ready_to_train;
  if (!ready) return null;
  const s = form.scales;
  return {
    answered_at_ms: now.getTime(),
    tz_offset_min: -now.getTimezoneOffset(),
    survey_version: 'v2',
    answers: {
      ready_to_train: ready,
      sleep_quality: s.sleep_quality ?? null,
      fatigue: s.fatigue ?? null,
      energy: s.energy ?? null,
      stress: s.stress ?? null,
      motivation: s.motivation ?? null,
      hydration: s.hydration ?? null,
      soreness: s.soreness ?? null,
      // Nothing tapped on the map isn't the same as "not sore anywhere", so it's left unanswered.
      sore_muscles: form.sore.length ? form.sore : null,
      unusual: form.unusual,
      rehydrated: askRehydrate ? form.rehydrated : null,
    },
  };
}
