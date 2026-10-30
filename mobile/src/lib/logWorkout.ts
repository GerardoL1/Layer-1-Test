/**
 * The "Log a workout" form: checking what was typed and turning it into a workout for the server.
 * Dates are "2026-10-01" and times "18:10", the form the pickers give. No imports, so
 * scripts/check-convert.js can test it without an iPhone.
 */
export const WORKOUT_PICKS = ['Run', 'Ride', 'Strength', 'Leg day', 'Upper body'];
export const MAX_NAME = 40;
const MAX_MINUTES = 24 * 60;

export type WorkoutForm = { name: string; date: string; time: string; length: string };
export type WorkoutErrors = Partial<Record<'name' | 'time' | 'length', string>>;

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pad = (n: number) => String(n).padStart(2, '0');

/** "2026-10-01" for a moment, in the phone's own time zone. */
export const dateValue = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
/** "18:10" for a moment, in the phone's own time zone. */
export const timeValue = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

/** The local moment a date and time stand for. Calendar maths, so clock-change days are fine. */
export function localMoment(date: string, time: string): Date {
  const [y, mo, d] = date.split('-').map(Number);
  const [h, mi] = (time || '00:00').split(':').map(Number);
  return new Date(y, mo - 1, d, h, mi);
}

/** "Wed 1 Oct" */
export function dateText(date: string): string {
  const d = localMoment(date, '00:00');
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** "6:10 pm" */
export function timeText(time: string): string {
  const [h, m] = time.split(':').map(Number);
  return `${h % 12 === 0 ? 12 : h % 12}:${pad(m)} ${h < 12 ? 'am' : 'pm'}`;
}

/** Every problem at once, so the person can fix them all in one go. */
export function checkWorkout(f: WorkoutForm, now: Date): WorkoutErrors {
  const errors: WorkoutErrors = {};
  if (!f.name.trim()) errors.name = 'Type a name for the workout.';
  const minutes = Number(f.length.trim());
  if (!/^\d+$/.test(f.length.trim()) || minutes < 1 || minutes > MAX_MINUTES) {
    errors.length = 'Type a length between 1 and 1,440 minutes.';
  }
  if (!f.time) errors.time = 'Pick a start time.';
  else if (localMoment(f.date, f.time) > now) errors.time = 'The workout can’t start in the future.';
  return errors;
}

/**
 * What the server's workouts route takes. Each end keeps its own UTC offset, so a workout across a clock
 * change is still right. The id only has to be new and URL-safe.
 */
export function workoutBody(f: WorkoutForm, id: string) {
  const start = localMoment(f.date, f.time);
  const end = new Date(start.getTime() + Number(f.length.trim()) * 60000);
  return {
    id,
    start_ms: start.getTime(),
    end_ms: end.getTime(),
    start_tz_min: -start.getTimezoneOffset(),
    end_tz_min: -end.getTimezoneOffset(),
    source: 'manual' as const,
    type: f.name.trim().slice(0, MAX_NAME),
  };
}
