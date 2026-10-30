/**
 * Today > Morning check-in (Figma "Check-in v2"). Three short steps on iPhone, one page on a computer.
 * Only "How ready" is required. The answers label last night, which is what the readiness model learns from.
 * Opened again the same day, the saved answers are filled in and saving replaces them.
 */
import { router } from 'expo-router';
import { useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { BodyMap } from '../../components/BodyMap';
import { Button } from '../../components/Button';
import { Chips } from '../../components/Editors';
import { LiveText } from '../../components/LiveText';
import { Page, PageState } from '../../components/Page';
import { RatingScale } from '../../components/RatingScale';
import { StepBar } from '../../components/SetupFrame';
import { Text } from '../../components/Text';
import {
  CheckinForm, checkinBody, EMPTY_FORM, formFrom, nightFor, REHYDRATED, SCALES, ScaleKey, STEP_SCALES, toggleMuscle,
  toggleUnusual, UNUSUAL, yesterdaysWorkout,
} from '../../lib/checkin';
import { dayLabel } from '../../lib/format';
import { errorText, useLoad } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';

const STEPS = [
  { title: 'Good morning. How do you feel?', intro: 'About a minute. 10 is always the good end.' },
  { title: 'And your energy and mood?', intro: 'Four more. 10 is always the good end.' },
  { title: 'Last one: your muscles', intro: 'Tap any sore muscles on the body. Tap again to remove.' },
];
const NEED_READY = 'Pick how ready you feel to train.';

// "Run" reads as "run" in a sentence, but "HIIT" keeps its capitals.
const sentenceCase = (t: string) => (t === t.toUpperCase() ? t : t.toLowerCase());
const leave = () => (router.canGoBack() ? router.back() : router.replace('/today'));

/** "‹ Today" or "‹ Back", where SubPageHeader puts its back link. */
function BackLink({ label, spoken, onPress }: { label: string; spoken: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="link" accessibilityLabel={spoken} onPress={onPress} style={styles.back}>
      <Text variant="button" color="textSecondary">‹ {label}</Text>
    </Pressable>
  );
}

/** Loads the person's clock and any answers already saved for the night, then shows the form. */
export default function CheckinScreen() {
  const api = useApi();
  const today = useLoad(() => api.today(), api);
  const nowLocal = today.data?.now_local ?? null;
  const key = useMemo(() => ({ api, nowLocal }), [api, nowLocal]);
  const saved = useLoad(() => (nowLocal ? api.morningCheckin(nightFor(nowLocal)) : Promise.resolve(null)), key);
  const error = today.error ?? saved.error;
  if (!nowLocal || saved.loading || error) {
    return <Page><PageState loading={!error} error={error} onRetry={() => (today.error ? today.reload() : saved.reload())} /></Page>;
  }
  return <CheckinFormScreen nowLocal={nowLocal} initial={saved.data ? formFrom(saved.data.answers) : null} />;
}

function CheckinFormScreen({ nowLocal, initial }: { nowLocal: string; initial: CheckinForm | null }) {
  const api = useApi();
  const { isWide } = useTheme();
  const [form, setForm] = useState<CheckinForm>(initial ?? EMPTY_FORM);
  const [step, setStep] = useState(0);
  const [needReady, setNeedReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // A ref, not state: two taps in the same moment both see state from before the first one.
  const busy = useRef(false);
  // When the step last changed. Next and Save sit in the same spot, so a quick double tap mustn't skip a step.
  const stepAt = useRef(0);
  // The rehydrate question is only for mornings after a workout. If this fails it's just not asked.
  const workouts = useLoad(() => api.workouts(2), api);
  const yesterday = workouts.data ? yesterdaysWorkout(workouts.data, nowLocal) : null;

  function pickScale(key: ScaleKey, n: number) {
    setForm((f) => ({ ...f, scales: { ...f.scales, [key]: n } }));
    if (key === 'ready_to_train') setNeedReady(false);
  }

  function goTo(n: number) {
    stepAt.current = Date.now();
    setStep(n);
  }

  function next() {
    if (Date.now() - stepAt.current < 500) return;
    if (step === 0 && !form.scales.ready_to_train) return setNeedReady(true);
    goTo(step + 1);
  }

  async function save() {
    if (busy.current || Date.now() - stepAt.current < 500) return;
    // Until the workouts load, the only rehydrate answer the form can hold is the saved one, so keep it.
    const body = checkinBody(form, new Date(), workouts.data ? !!yesterday : true);
    if (!body) {
      setNeedReady(true);
      if (!isWide) setStep(0);
      return;
    }
    busy.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await api.saveCheckin(body);
      // The server keeps the newest answer, so an older one (a phone clock running behind) isn't saved.
      if (saved.answered_at_ms !== body.answered_at_ms) {
        setSaveError('A newer answer is already saved, so this one wasn’t. Check this phone’s clock.');
        return;
      }
      router.replace('/today');
    } catch (e) {
      setSaveError(`Couldn’t save. ${errorText(e)}`);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  const scale = (key: ScaleKey) => {
    const q = SCALES.find((s) => s.key === key)!;
    return (
      <View key={key}>
        <RatingScale question={q.question} low={q.low} high={q.high} value={form.scales[key]} disabled={saving}
          onPick={(n) => pickScale(key, n)} />
        {key === 'ready_to_train' && needReady ? (
          <LiveText error variant="bodySmall" color="low" style={styles.error}>{NEED_READY}</LiveText>
        ) : null}
      </View>
    );
  };

  const muscles = (
    <>
      {isWide ? (
        <View style={styles.where}>
          <Text variant="bodyEmphasis">Where are you sore?</Text>
          <Text variant="body" color="textSecondary">Click the sore muscles. Click again to remove.</Text>
        </View>
      ) : null}
      <BodyMap sore={form.sore} disabled={saving} onToggle={(m) => setForm((f) => ({ ...f, sore: toggleMuscle(f.sore, m) }))} />
      <View style={styles.chipQuestion}>
        <Text variant="bodyEmphasis">Anything unusual since yesterday?</Text>
        <Chips name="Anything unusual since yesterday?" options={UNUSUAL}
          // "None" is saved as an empty list, and shows as its own chip.
          value={form.unusual === null ? [] : form.unusual.length ? form.unusual : ['none' as const]}
          onPick={(v) => (saving ? undefined : setForm((f) => ({ ...f, unusual: toggleUnusual(f.unusual, v) })))} />
      </View>
      {yesterday ? (
        <View style={styles.chipQuestion}>
          <Text variant="bodyEmphasis">{`Did you rehydrate after yesterday’s ${sentenceCase(yesterday.type)}?`}</Text>
          <Chips name="Did you rehydrate?" options={REHYDRATED} value={form.rehydrated}
            onPick={(v) => (saving ? undefined : setForm((f) => ({ ...f, rehydrated: v })))} />
        </View>
      ) : null}
    </>
  );

  const ending = (
    <>
      {saveError ? <LiveText error variant="bodySmall" color="low" style={styles.saveError}>{saveError}</LiveText> : null}
      <View style={[styles.actions, isWide && styles.actionsWide]}>
        {isWide || step === 2
          ? <Button title="Save check-in" busy={saving} busyTitle="Saving…" onPress={save} />
          : <Button title="Next" onPress={next} />}
        {/* Changing answers already saved is something to back out of, not a morning to skip. */}
        <Button title={initial ? 'Cancel' : 'Skip today'} kind="text" disabled={saving} onPress={leave} />
      </View>
    </>
  );

  if (isWide) {
    return (
      <Page>
        <Text variant="bodySmall" color="textSecondary">{`${dayLabel(nowLocal)} · morning check-in`}</Text>
        <Text variant="h1" accessibilityRole="header" style={styles.title}>{STEPS[0].title}</Text>
        <Text variant="body" color="textSecondary" style={styles.introWide}>
          About a minute. 10 is always the good end. Your answers teach the scores what your normal feels like.
        </Text>
        <View style={styles.columns}>
          <View style={styles.wideColumn}>{[...STEP_SCALES[0], ...STEP_SCALES[1]].map(scale)}</View>
          <View style={styles.wideColumn}>{STEP_SCALES[2].map(scale)}{muscles}</View>
        </View>
        {ending}
      </Page>
    );
  }

  // A new Page per step, so each step starts at the top. Going back keeps every answer.
  return (
    <Page key={step}>
      {step === 0
        ? <BackLink label="Today" spoken="Back to Today" onPress={leave} />
        : <BackLink label="Back" spoken={`Back to step ${step}`} onPress={() => goTo(step - 1)} />}
      <StepBar label={`Morning check-in · ${step + 1} of 3`} step={step + 1} />
      <Text variant="h1" accessibilityRole="header">{STEPS[step].title}</Text>
      <Text variant="body" color="textSecondary" style={styles.intro}>{STEPS[step].intro}</Text>
      <View style={styles.column}>
        {STEP_SCALES[step].map(scale)}
        {step === 2 ? muscles : null}
      </View>
      {ending}
    </Page>
  );
}

const styles = StyleSheet.create({
  back: { alignSelf: 'flex-start', minHeight: 44, justifyContent: 'center', marginBottom: 8 },
  title: { marginTop: 8 },
  intro: { marginTop: 12, marginBottom: 24 },
  introWide: { marginTop: 8, marginBottom: 32, maxWidth: 580 },
  // Two columns only when each has room for ten rating buttons and the body map, otherwise they stack.
  columns: { flexDirection: 'row', flexWrap: 'wrap', gap: 56 },
  wideColumn: { flexGrow: 1, flexBasis: 340, gap: 32 },
  column: { flex: 1, gap: 32 },
  where: { gap: 8 },
  chipQuestion: { gap: 12 },
  error: { marginTop: 8 },
  saveError: { marginTop: 24 },
  actions: { marginTop: 32, gap: 12 },
  actionsWide: { flexDirection: 'row', alignItems: 'center' },
});
