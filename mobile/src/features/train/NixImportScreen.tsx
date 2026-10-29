/**
 * Import a Nix export: choose the file, check what it says, pick the workout when it doesn't match,
 * then save. Figma "Round 4 · Nix import" (Add sweat data, Check your import, Which workout is this?,
 * We couldn't read this file).
 *
 * It's one screen with steps, so the picked file stays in memory between them. The server saves nothing
 * until Save, which sends the same file again. Leaving or reloading simply drops the file.
 * Every workout picked is checked with the server again, so the notes say what saving to that one does.
 */
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useRef, useState } from 'react';
import { Platform, StyleSheet, View } from 'react-native';

import { ApiError, MAX_NIX_BYTES, NixPreview, NixTarget, UploadFile, Workout } from '../../api/client';
import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { DropZone } from '../../components/DropZone';
import { ListRow } from '../../components/ListRow';
import { LiveText } from '../../components/LiveText';
import { Notice } from '../../components/Notice';
import { NumberedSteps } from '../../components/NumberedSteps';
import { Page } from '../../components/Page';
import { Panel } from '../../components/Panel';
import { SectionHeader } from '../../components/SectionHeader';
import { SubPageHeader } from '../../components/SubPageHeader';
import { Text } from '../../components/Text';
import { pickNix } from '../../lib/pickNix';
import {
  alsoSaved,
  checkLabel,
  duration,
  existingNote,
  isRefused,
  joined,
  movesNote,
  notThisWorkout,
  sessionStats,
  spanLabel,
  startLabel,
  Units,
} from '../../lib/sweat';
import { errorText, useLoad } from '../../lib/useLoad';
import { weightText } from '../../lib/weight';
import { useTheme } from '../../theme/theme';
import { Announce } from './Announce';
import { LoadState } from './LoadState';

const STEPS_PHONE = [
  'Open Insights, then Workouts.',
  'Pick this workout and scroll to the bottom.',
  'Tap Export Workout.',
  'Save to Files, then choose it here.',
];
const STEPS_WEB = [...STEPS_PHONE.slice(0, 3), 'Get the file onto this device, then choose or drop it here.'];
const NO_SWEAT = "Nix didn't pick up any sweat this session. Only breathing loss was recorded, so this won't count "
  + 'as sweat data.';
const TOO_BIG = 'This file is far bigger than a Nix export (about 160 KB). Use the Excel file from Export Workout '
  + 'in the Nix app.';

type Target = { save: NixTarget; label: string };
/** Why the workout list shows: the file isn't from the workout we came from, nothing matched, or a change. */
type PickReason = 'not-this' | 'no-match' | 'change';
type Step =
  | { kind: 'choose'; problem?: string }
  | { kind: 'reading' }
  | { kind: 'check'; file: UploadFile; preview: NixPreview; target: Target }
  | { kind: 'pick'; file: UploadFile; preview: NixPreview; reason: PickReason; problem?: string }
  | { kind: 'unreadable'; fileName: string; message: string };

/** "Thu 25 Sep · Leg day", how a workout row names a workout. */
const workoutName = (w: Workout) => `${startLabel(w.start_local).split(' · ')[0]} · ${w.type}`;

export default function NixImportScreen() {
  const api = useApi();
  const { isWide } = useTheme();
  const { workoutId } = useLocalSearchParams<{ workoutId?: string }>();
  const key = useMemo(() => ({ api, workoutId }), [api, workoutId]);
  const base = useLoad(async () => {
    const [settings, from, fromSweat] = await Promise.all([
      api.settings(),
      workoutId ? api.workout(workoutId) : null,
      workoutId ? api.workoutSweat(workoutId).catch(() => null) : null,
    ]);
    return { workoutId, settings, from, fromSweat };
  }, key);
  const [step, setStep] = useState<Step>({ kind: 'choose' });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [weight, setWeight] = useState<{ busy: boolean; saved: boolean; error: string | null }>(
    { busy: false, saved: false, error: null });
  // The workout being checked (or 'new'), so its row can say "Checking…".
  const [checking, setChecking] = useState<string | null>(null);
  // A ref, not state: two taps in the same moment both see state from before the first one.
  const busy = useRef(false);

  // Opened for another workout without leaving the screen: start over, the picked file belongs to the old one.
  // Done while rendering (React's way to reset state when an input changes), not in an effect.
  const [stepFor, setStepFor] = useState(workoutId);
  if (stepFor !== workoutId) {
    setStepFor(workoutId);
    setStep({ kind: 'choose' });
    setSaveError(null);
  }

  const current = base.data && base.data.workoutId === workoutId ? base.data : null;
  const back = current?.from?.type ?? 'Train';
  const home = workoutId ? { pathname: '/train/workout/[workoutId]' as const, params: { workoutId } } : '/train';
  if (!current) {
    return (
      <Page>
        <SubPageHeader back={back} home={home} label="Sweat data" title="Add sweat data" />
        <LoadState loading={base.loading || !!base.data} error={base.error} onRetry={base.reload} />
      </Page>
    );
  }
  const { settings, from, fromSweat } = current;
  const units = settings.units as Units;

  function reset() {
    setSaveError(null);
    setWeight({ busy: false, saved: false, error: null });
  }

  async function read(file: UploadFile) {
    if (busy.current) return;
    if (file.size !== undefined && file.size > MAX_NIX_BYTES) {
      setStep({ kind: 'choose', problem: TOO_BIG });
      return;
    }
    busy.current = true;
    reset();
    setStep({ kind: 'reading' });
    try {
      const preview = await api.previewNix(file);
      const matched = preview.matched_workout;
      if (from) {
        // Opened from a workout: go straight on only when the file is from that workout.
        if (matched?.id === from.id) setStep({ kind: 'check', file, preview, target: { save: { workoutId: from.id }, label: workoutName(from) } });
        else setStep({ kind: 'pick', file, preview, reason: 'not-this' });
      } else if (matched) {
        setStep({ kind: 'check', file, preview, target: { save: { workoutId: matched.id }, label: workoutName(matched) } });
      } else {
        setStep({ kind: 'pick', file, preview, reason: 'no-match' });
      }
    } catch (e) {
      // A 400 is the server saying what's wrong with the file. Anything else (no connection) isn't the file's fault.
      if (e instanceof ApiError && e.status === 400) setStep({ kind: 'unreadable', fileName: file.name, message: e.message });
      else setStep({ kind: 'choose', problem: errorText(e) });
    } finally {
      busy.current = false;
    }
  }

  async function choose() {
    try {
      const file = await pickNix();
      if (file) await read(file);
    } catch (e) {
      setStep({ kind: 'choose', problem: errorText(e) });
    }
  }

  /** A workout was picked: ask the server again, so the notes are about saving to this one. */
  async function checkFor(file: UploadFile, preview: NixPreview, reason: PickReason, target: Target) {
    if (busy.current) return;
    busy.current = true;
    setChecking('workoutId' in target.save ? target.save.workoutId : 'new');
    reset();
    try {
      const fresh = await api.previewNix(file, target.save);
      // A new workout for this file may already exist from an earlier save, so name that one.
      const made = 'newWorkout' in target.save && fresh.session.workout_id
        ? await api.workout(fresh.session.workout_id).catch(() => null) : null;
      setStep({ kind: 'check', file, preview: fresh, target: made ? { ...target, label: workoutName(made) } : target });
    } catch (e) {
      setStep({ kind: 'pick', file, preview, reason, problem: `Couldn't check this workout. ${errorText(e)}` });
    } finally {
      busy.current = false;
      setChecking(null);
    }
  }

  async function save(file: UploadFile, target: Target) {
    if (busy.current) return;
    busy.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await api.saveNix(file, target.save);
      const savedTo = saved.workout_id ?? ('workoutId' in target.save ? target.save.workoutId : null);
      // Back to the workout we came from when that's where it was saved, so Back after that goes to Train.
      if (savedTo && savedTo === workoutId && router.canGoBack()) router.back();
      else if (savedTo) router.replace({ pathname: '/train/workout/[workoutId]', params: { workoutId: savedTo } });
      else router.replace('/train');
    } catch (e) {
      setSaveError(`Couldn't save. ${errorText(e)}`);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  async function saveWeight(kg: number) {
    if (weight.busy) return;
    setWeight({ busy: true, saved: false, error: null });
    try {
      await api.saveSettings({ weight_kg: kg });
      setWeight({ busy: false, saved: true, error: null });
    } catch (e) {
      setWeight({ busy: false, saved: false, error: errorText(e) });
    }
  }

  // Typing numbers in can't replace Nix sweat data (that's refused), so it's only offered when it could work.
  const nixAlready = !!fromSweat && fromSweat.source === 'nix' && fromSweat.sweat_detected;
  const typeByHand = from && !nixAlready ? (
    <Button title="Enter numbers by hand" kind="secondary" style={styles.space12}
      onPress={() => router.replace({ pathname: '/train/log', params: { workoutId: from.id } })} />
  ) : null;
  const fromRow = from ? <Panel style={styles.space16}><ListRow label="Workout" value={workoutName(from)} /></Panel> : null;
  const steps = (
    <View style={styles.space24}>
      <SectionHeader title="In the Nix app" note="4 steps" />
      {/* "this workout" only makes sense when the import was opened from one. */}
      <NumberedSteps steps={(Platform.OS === 'web' ? STEPS_WEB : STEPS_PHONE)
        .map((t) => (from ? t : t.replace('this workout', 'the workout')))} />
      <Text variant="bodySmall" color="textMuted" style={styles.space12}>
        Set Nix to Metric for the most accurate numbers. Import after each workout so tomorrow’s readiness includes it.
      </Text>
    </View>
  );

  // ---------------------------------------------------------------- Add sweat data
  if (step.kind === 'choose' || step.kind === 'reading') {
    const reading = step.kind === 'reading';
    const picker = Platform.OS === 'web' ? (
      <DropZone title="Drop the Nix .xlsx here" accept=".xlsx" disabled={reading}
        onFile={(f) => read({ name: f.name, part: f, size: f.size })}
        note="The Excel file from Export Workout in the Nix app." />
    ) : (
      <Button title="Choose Nix file" busy={reading} onPress={choose} />
    );
    const actions = (
      <View style={styles.space24}>
        {picker}
        {reading ? <LiveText color="textSecondary" style={styles.space12}>Reading the file…</LiveText> : null}
        {step.kind === 'choose' && step.problem ? (
          <LiveText error color="low" style={styles.space12}>{step.problem}</LiveText>
        ) : null}
        {typeByHand}
      </View>
    );
    return (
      <Page>
        <SubPageHeader back={back} home={home} label="Sweat data" title="Add sweat data"
          intro="Import the workout file from your Nix app. It takes about 30 seconds." />
        {isWide ? (
          <View style={styles.columns}>
            <View style={styles.column}>{fromRow}{steps}</View>
            <View style={styles.column}>{actions}</View>
          </View>
        ) : (
          <>
            {fromRow}
            {steps}
            {actions}
          </>
        )}
      </Page>
    );
  }

  // ---------------------------------------------------------------- We couldn't use this file
  if (step.kind === 'unreadable') {
    return (
      <Page>
        <Announce text="We couldn’t use this file." />
        <SubPageHeader back={back} home={home} label="Nix file" title="We couldn’t use this file"
          intro="Here’s what’s wrong with it. Export the workout again from the Nix app if you can." />
        {/* The file name goes in the text, so it keeps its own capitals. */}
        <Notice type="warning" label="Nix file" live>{`${step.fileName || 'The file'}: ${step.message}`}</Notice>
        {fromRow}
        {steps}
        <Button title="Choose another file" style={styles.space24} onPress={() => setStep({ kind: 'choose' })} />
        {typeByHand}
      </Page>
    );
  }

  const { file, preview } = step;
  const s = preview.session;
  const fileTimes = `${spanLabel(s.start_local, s.end_local)} · ${duration(s.duration_min)}`;

  // ---------------------------------------------------------------- Which workout is this?
  if (step.kind === 'pick') {
    const { reason } = step;
    const matched = preview.matched_workout;
    const seen = new Set<string>();
    // Best match first, then nearby ones. The workout we came from has its own row when the file isn't from it.
    const options = [...(matched ? [matched] : []), ...preview.nearby_workouts, ...(from ? [from] : [])]
      .filter((w) => !seen.has(w.id) && !!seen.add(w.id))
      .filter((w) => !(reason === 'not-this' && w.id === from?.id));
    const pick = (w: Workout) =>
      checkFor(file, preview, reason, { save: { workoutId: w.id }, label: workoutName(w) });
    const intro = reason === 'not-this' ? notThisWorkout(s.start_local)
      : reason === 'no-match' ? `This file is from ${spanLabel(s.start_local, s.end_local)}. No workout from your Apple Watch matches that time.`
        : `This file is from ${spanLabel(s.start_local, s.end_local)}. Pick the workout it belongs to.`;
    return (
      <Page>
        <Announce text={`Which workout is this? ${intro}`} />
        <SubPageHeader back={back} home={home} label="Nix file" title="Which workout is this?" intro={intro} />
        {options.length || (from && reason === 'not-this') ? (
          <View style={styles.space8}>
            <SectionHeader title="Pick a workout" note={matched ? 'Best match first' : 'Closest first'} />
            <Panel>
              {options.map((w) => (
                <ListRow key={w.id} label={workoutName(w)} value={checking === w.id ? 'Checking…'
                  : w.id === matched?.id ? 'Matches the file' : startLabel(w.start_local).split(' · ')[1]}
                  onPress={checking ? undefined : () => pick(w)} />
              ))}
              {from && reason === 'not-this' ? (
                <ListRow label={`Save to ${from.type} anyway`} value={checking === from.id ? 'Checking…' : null}
                  onPress={checking ? undefined : () => pick(from)} />
              ) : null}
            </Panel>
          </View>
        ) : null}
        {step.problem ? <LiveText error color="low" style={styles.space12}>{step.problem}</LiveText> : null}
        <Text variant="bodySmall" color="textMuted" style={styles.space12}>
          Not listed? Save it as a new workout using the times in the file.
        </Text>
        <Button title="Save as a new workout" style={styles.space16} busy={checking === 'new'} disabled={!!checking}
          onPress={() => checkFor(file, preview, reason,
            { save: { newWorkout: true }, label: `New workout · ${s.workout_type ?? 'Workout'}` })} />
        <Button title="Choose a different file" kind="secondary" style={styles.space12} disabled={!!checking}
          onPress={() => setStep({ kind: 'choose' })} />
      </Page>
    );
  }

  // ---------------------------------------------------------------- Check your import
  // The preview on screen was made for this target, so its notes are about saving here.
  const { target } = step;
  const note = existingNote(preview.existing);
  const blocked = isRefused(preview.existing);
  const moves = preview.moves_from_workout ? movesNote(workoutName(preview.moves_from_workout)) : null;
  const matchedHere = 'workoutId' in target.save && target.save.workoutId === preview.matched_workout?.id;
  const extras = alsoSaved(s);
  const otherWarnings = s.warnings.filter((w) => !w.startsWith("Nix didn't pick up any sweat"));
  const suggestion = preview.weight_suggestion_kg;

  const numbers = (
    <View style={styles.space24}>
      <SectionHeader title="Sweat" note="From Nix" />
      <Panel>
        {sessionStats(s, units).map((x) => (
          <ListRow key={x.label} label={checkLabel(x.label)} value={x.shown ? joined(x.shown) : 'Not measured'} />
        ))}
      </Panel>
      {!s.sweat_detected ? (
        <View style={styles.space12}><Notice type="warning" label="No sweat picked up" live>{NO_SWEAT}</Notice></View>
      ) : null}
      {extras ? <Text variant="bodySmall" color="textMuted" style={styles.space12}>{extras}</Text> : null}
      <Text variant="bodySmall" color="textMuted" style={styles.space8}>
        Nix counts sweat only after about 15 minutes, so the start of a workout reads low.
      </Text>
    </View>
  );
  // Figma puts these at the top, right under the intro, so they're seen before the numbers.
  const notices = otherWarnings.length || note || moves ? (
    <View style={styles.notices}>
      {otherWarnings.map((w, i) => <Notice key={`${i}-${w}`} type="info" label="Check the numbers" live>{w}</Notice>)}
      {note ? <Notice type={blocked ? 'warning' : 'info'} label="Already saved" live>{note}</Notice> : null}
      {moves ? <Notice type="warning" label="Moves sweat data" live>{moves}</Notice> : null}
    </View>
  ) : null;
  const weightOffer = suggestion ? (
    <View style={styles.weight}>
      <Text variant="body" style={styles.fill}>{`Use ${weightText(suggestion, units)} from your Nix file?`}</Text>
      {weight.saved ? <LiveText variant="bodySmall" color="textSecondary">Saved to your Settings.</LiveText>
        : <Button title="Use it" kind="secondary" busy={weight.busy} onPress={() => saveWeight(suggestion)} />}
      {weight.error ? <LiveText error variant="bodySmall" color="low">{weight.error}</LiveText> : null}
    </View>
  ) : null;
  const actions = (
    <View style={styles.space24}>
      {saveError ? <LiveText error color="low" style={styles.space12}>{saveError}</LiveText> : null}
      <Button title="Save sweat data" busy={saving} disabled={blocked} onPress={() => save(file, target)} />
      <Button title="Choose a different file" kind="secondary" style={styles.space12} disabled={saving}
        onPress={() => setStep({ kind: 'choose' })} />
    </View>
  );
  const rows = (
    <Panel style={styles.space16}>
      <ListRow label="Workout" value={target.label} hint="Changes which workout this is saved to"
        onPress={() => setStep({ kind: 'pick', file, preview, reason: 'change' })} />
      <ListRow label="Nix file" value={fileTimes} />
    </Panel>
  );
  return (
    <Page>
      <Announce text="Check your import." />
      <SubPageHeader back={back} home={home} label="Nix file" title="Check your import"
        intro={matchedHere ? 'We matched this file to your workout. Check the numbers, then save.'
          : 'Check the numbers, then save.'} />
      {notices}
      {isWide ? (
        <View style={styles.columns}>
          <View style={styles.column}>{rows}{numbers}</View>
          <View style={styles.column}>{weightOffer}{actions}</View>
        </View>
      ) : (
        <>
          {rows}
          {numbers}
          {weightOffer}
          {actions}
        </>
      )}
    </Page>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  columns: { flexDirection: 'row', gap: 56 },
  column: { flex: 1 },
  notices: { marginTop: 8, gap: 14 },
  weight: { flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginTop: 20 },
  space8: { marginTop: 8 },
  space12: { marginTop: 12 },
  space16: { marginTop: 16 },
  space24: { marginTop: 24 },
});
