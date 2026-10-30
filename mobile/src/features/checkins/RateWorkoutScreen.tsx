/**
 * Workout summary > "How was it?": the after-workout check-in (Figma "After-workout check-in").
 * How hard is required, since effort times minutes is the training load. Rating again replaces the answer.
 */
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Workout } from '../../api/client';
import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { LiveText } from '../../components/LiveText';
import { Page, PageState } from '../../components/Page';
import { RatingScale } from '../../components/RatingScale';
import { SubPageHeader } from '../../components/SubPageHeader';
import { spanLabel } from '../../lib/sweat';
import { errorText, useLoad } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';

export default function RateWorkoutScreen() {
  const api = useApi();
  const { workoutId } = useLocalSearchParams<{ workoutId: string }>();
  const key = useMemo(() => ({ api, workoutId }), [api, workoutId]);
  const { data, error, reload } = useLoad(() => api.workout(workoutId), key);
  // Old data from another workout is never shown under this one's address.
  if (!data || data.id !== workoutId) {
    return (
      <Page>
        <SubPageHeader back="Workout" home={summary(workoutId)} label="Workout" />
        <PageState loading={!error} error={error} onRetry={reload} />
      </Page>
    );
  }
  return <RateForm workout={data} />;
}

const summary = (workoutId: string) => ({ pathname: '/train/workout/[workoutId]', params: { workoutId } }) as const;

function RateForm({ workout: w }: { workout: Workout }) {
  const api = useApi();
  const { isWide } = useTheme();
  const rated = w.effort !== null;
  const [effort, setEffort] = useState<number | null>(w.effort);
  const [happy, setHappy] = useState<number | null>(w.satisfaction);
  const [needEffort, setNeedEffort] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // A ref, not state: two taps in the same moment both see state from before the first one.
  const busy = useRef(false);
  const leave = () => (router.canGoBack() ? router.back() : router.replace(summary(w.id)));

  async function save() {
    if (busy.current) return;
    if (effort === null) return setNeedEffort(true);
    busy.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      await api.rateWorkout(w.id, { effort, satisfaction: happy, answered_at_ms: Date.now() });
      leave();
    } catch (e) {
      setSaveError(`Couldn’t save. ${errorText(e)}`);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  // "Mon 29 Sep · 6:10–7:08 pm": the day only on a computer, like Figma.
  const [day, ...time] = spanLabel(w.start_local, w.end_local).split(' · ');
  const when = `${w.type} · ${time.join(' · ')}`;
  return (
    <Page>
      <View style={styles.column}>
        <SubPageHeader back={w.type} home={summary(w.id)} label="Workout" title="Nice work. How was it?"
          detail={isWide ? `${day} · ${when}` : when}
          intro={`Two ${isWide ? 'clicks' : 'taps'}. Effort × time is how the app measures training load.`} />
        <View style={styles.questions}>
          <View>
            <RatingScale question="How hard was that workout?" low="Very easy" high="Max effort" value={effort}
              disabled={saving} onPick={(n) => { setEffort(n); setNeedEffort(false); }} />
            {needEffort ? <LiveText error variant="bodySmall" color="low" style={styles.error}>Pick how hard it was.</LiveText> : null}
          </View>
          <RatingScale question="How happy are you with how it went?" low="Not at all" high="Very happy" value={happy}
            disabled={saving} onPick={setHappy} />
        </View>
        {saveError ? <LiveText error variant="bodySmall" color="low" style={styles.saveError}>{saveError}</LiveText> : null}
        <View style={[styles.actions, isWide && styles.actionsWide]}>
          <Button title="Save" busy={saving} busyTitle="Saving…" onPress={save} />
          <Button title={rated ? 'Cancel' : 'Skip'} kind="text" disabled={saving} onPress={leave} />
        </View>
      </View>
    </Page>
  );
}

const styles = StyleSheet.create({
  column: { maxWidth: 476 },
  questions: { marginTop: 24, gap: 32 },
  error: { marginTop: 8 },
  saveError: { marginTop: 24 },
  actions: { marginTop: 32, gap: 12 },
  actionsWide: { flexDirection: 'row', alignItems: 'center' },
});
