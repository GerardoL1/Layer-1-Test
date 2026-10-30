/**
 * Train > Log a workout: a workout the watch didn't record, typed in by hand. Same layout as Log a sweat
 * session. Saved through the Layer 1 workouts route as source "manual", then its summary opens.
 */
import { router } from 'expo-router';
import { useRef, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { Chips } from '../../components/Editors';
import { ListRow } from '../../components/ListRow';
import { LiveText } from '../../components/LiveText';
import { NumberedSteps } from '../../components/NumberedSteps';
import { Page } from '../../components/Page';
import { Panel } from '../../components/Panel';
import { SectionHeader } from '../../components/SectionHeader';
import { SubPageHeader } from '../../components/SubPageHeader';
import { Text } from '../../components/Text';
import { fieldError } from '../../lib/a11y';
import { checkWorkout, dateValue, MAX_NAME, WORKOUT_PICKS, WorkoutErrors, WorkoutForm, workoutBody } from '../../lib/logWorkout';
import { errorText } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';
import { radius, type } from '../../theme/tokens';
import { DateTimeField } from './DateTimeField';

const AFTER_SAVE = [
  'The workout’s summary opens.',
  'Add sweat data from there, if you have it.',
  'It shows in Train and All workouts as “Added in the app”.',
];

/** A tinted text box with its label and error, like Log a sweat session's fields. */
function Box({ id, label, value, onChange, placeholder, error, unit, number, editable, spoken }: {
  id: string; label: string; value: string; onChange: (t: string) => void; placeholder: string;
  error?: string; unit?: string; number?: boolean; editable: boolean; spoken: string;
}) {
  const { colors } = useTheme();
  const [focused, setFocused] = useState(false);
  const lineColor = error ? colors.low : focused ? colors.link : 'transparent';
  return (
    <View style={styles.field}>
      <Text variant="bodySmall" color={error ? 'low' : 'textSecondary'}>{label}</Text>
      <View style={[styles.box, { borderColor: lineColor, backgroundColor: colors.surface }]}>
        <TextInput value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.textMuted}
          keyboardType={number ? 'number-pad' : 'default'} maxLength={number ? 4 : MAX_NAME} editable={editable}
          autoCorrect={false} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          accessibilityLabel={spoken} {...fieldError(`${id}-error`, !!error)}
          style={[styles.input, { color: colors.textPrimary }]} />
        {unit ? <Text variant="bodySmall" color="textMuted" aria-hidden>{unit}</Text> : null}
      </View>
    </View>
  );
}

export default function LogWorkoutScreen() {
  const api = useApi();
  const { isWide } = useTheme();
  const [form, setForm] = useState<WorkoutForm>(() => ({ name: '', date: dateValue(new Date()), time: '', length: '' }));
  const [errors, setErrors] = useState<WorkoutErrors>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // A ref, not state: two taps in the same moment both see state from before the first one.
  const busy = useRef(false);
  // Made once, so trying Save again after a lost reply updates the same workout instead of adding a second.
  const [id] = useState(() => `logged-${Date.now().toString(36)}`);

  // An error goes away as soon as its field is edited.
  function set<K extends keyof WorkoutForm>(key: K, value: WorkoutForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    const field = key === 'date' ? 'time' : key;
    setErrors((e) => (field in e ? { ...e, [field]: undefined } : e));
  }

  async function save() {
    if (busy.current) return;
    const found = checkWorkout(form, new Date());
    setErrors(found);
    if (Object.values(found).some(Boolean)) return;
    busy.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      const w = await api.saveWorkout(workoutBody(form, id));
      // Replaced, so Back from the summary goes to Train rather than to this form.
      router.replace({ pathname: '/train/workout/[workoutId]', params: { workoutId: w.id } });
    } catch (e) {
      setSaveError(`Couldn't save. ${errorText(e)}`);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  const picked = WORKOUT_PICKS.includes(form.name) ? form.name : null;
  const fields = (
    <View style={styles.form}>
      {/* The other way to add a workout: a Nix file brings its own times, and the import matches or creates one. */}
      <Panel>
        <ListRow label="Import a Nix file" value=".xlsx" onPress={() => router.replace('/train/import')} />
      </Panel>
      <View style={styles.field}>
        <Box id="workout-name" label="Workout" spoken="Workout name" value={form.name} placeholder="e.g. Leg day"
          onChange={(t) => set('name', t)} error={errors.name} editable={!saving} />
        <Chips name="Quick picks" options={WORKOUT_PICKS.map((p) => ({ value: p, label: p }))} value={picked}
          onPick={(p) => (saving ? undefined : set('name', p))} />
        {errors.name ? <LiveText error nativeID="workout-name-error" variant="bodySmall" color="low">{errors.name}</LiveText> : null}
      </View>
      <DateTimeField id="workout-date" label="Date" mode="date" value={form.date} disabled={saving}
        onChange={(v) => set('date', v)} />
      <DateTimeField id="workout-time" label="Start time" mode="time" value={form.time} placeholder="e.g. 6:10 pm"
        disabled={saving} onChange={(v) => set('time', v)} error={errors.time} />
      <View style={styles.field}>
        <Box id="workout-length" label="Length" spoken="Length, in minutes" value={form.length} placeholder="e.g. 45"
          unit="min" number onChange={(t) => set('length', t)} error={errors.length} editable={!saving} />
        {errors.length ? <LiveText error nativeID="workout-length-error" variant="bodySmall" color="low">{errors.length}</LiveText> : null}
      </View>
      {saveError ? <LiveText error variant="bodySmall" color="low">{saveError}</LiveText> : null}
      <Button title="Save workout" busy={saving} onPress={save} />
      <Button title="Cancel" kind="secondary" disabled={saving}
        onPress={() => (router.canGoBack() ? router.back() : router.replace('/train'))} />
    </View>
  );

  return (
    <Page form>
      <SubPageHeader back="Train" home="/train" label="Workouts" title="Log a workout"
        intro="Add a workout your watch didn’t record. You can add sweat data to it after." />
      {isWide ? (
        <View style={styles.columns}>
          <View style={styles.column}>{fields}</View>
          <View style={styles.column}>
            <SectionHeader title="After you save" />
            <NumberedSteps steps={AFTER_SAVE} />
          </View>
        </View>
      ) : fields}
    </Page>
  );
}

const styles = StyleSheet.create({
  form: { marginTop: 8, gap: 18, maxWidth: 520 },
  field: { gap: 6 },
  box: { flexDirection: 'row', alignItems: 'center', borderWidth: 2, borderRadius: radius.sm, minHeight: 46,
    paddingHorizontal: 14, gap: 8 },
  // The teal or red outline is on the box around it. Chrome draws its own ring for the "auto" outline style
  // whatever its colour, so it's set to a solid ring 0 px wide instead.
  input: { ...type.body, flex: 1, minHeight: 44, paddingVertical: 8, outlineStyle: 'solid', outlineWidth: 0,
    borderWidth: 0, backgroundColor: 'transparent' },
  columns: { flexDirection: 'row', gap: 56 },
  column: { flex: 1 },
});
