/**
 * What the Train screens load: the person's local "now" and readiness (from Today), their workouts,
 * which workouts have sweat data, and their Units setting.
 */
import { useApi } from '../../api/useApi';
import { Units } from '../../lib/sweat';
import { useLoad } from '../../lib/useLoad';

export function useTrainData() {
  const api = useApi();
  return useLoad(async () => {
    const [today, workouts, sessions, settings] = await Promise.all([
      api.today(),
      api.workouts(),
      api.sweatSessions(),
      api.settings(),
    ]);
    return {
      // The server's clock for this person, which is fixed for demo people.
      nowLocal: today.now_local,
      status: today.readiness?.status ?? null,
      workouts,
      withSweat: new Set(sessions.map((s) => s.workout_id)),
      units: settings.units as Units,
    };
  }, api);
}

/** The data tags a workout row shows. PATCH joins this with Layer 2. */
export function tagsFor(workoutId: string, withSweat: Set<string | null>): string[] {
  return withSweat.has(workoutId) ? ['Sweat'] : [];
}
