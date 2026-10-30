/**
 * Log a sweat session: numbers typed in from any sweat sensor, for one workout. Figma "Log a sweat session".
 * Typed in the person's Units, saved in ml, mg and L/h. Numbers typed in before fill the boxes again.
 */
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useRef, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { ListRow } from '../../components/ListRow';
import { LiveText } from '../../components/LiveText';
import { Page, PageState } from '../../components/Page';
import { Panel } from '../../components/Panel';
import { SubPageHeader } from '../../components/SubPageHeader';
import { Text } from '../../components/Text';
import { fieldError } from '../../lib/a11y';
import { AmountKind, amountHint, amountInput, amountUnit, startLabel, typedValue, Units } from '../../lib/sweat';
import { errorText, useLoad } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';
import { radius, type } from '../../theme/tokens';

const FIELDS: { kind: AmountKind; label: string; spoken: string }[] = [
  { kind: 'fluid', label: 'Sweat loss', spoken: 'Sweat loss' },
  { kind: 'sodium', label: 'Sodium loss', spoken: 'Sodium loss, optional' },
  { kind: 'rate', label: 'Sweat rate (optional)', spoken: 'Sweat rate, optional' },
];
const UNIT_WORDS: Record<string, string> = { ml: 'millilitres', oz: 'ounces', mg: 'milligrams',
  'L/h': 'litres an hour', 'oz/h': 'ounces an hour' };
const EMPTY: Record<AmountKind, string> = { fluid: '', sodium: '', rate: '' };

/** A tinted box with its label, unit and error, like Figma's Text field: teal outline while typing, red on error. */
function Field({ id, label, spoken, unit, value, onChange, onSubmit, error, hint }: {
  id: string; label: string; spoken: string; unit: string; value: string; onChange: (t: string) => void;
  onSubmit: () => void; error: string | null; hint: string;
}) {
  const { colors } = useTheme();
  const [focused, setFocused] = useState(false);
  const lineColor = error ? colors.low : focused ? colors.link : 'transparent';
  return (
    <View style={styles.field}>
      <Text variant="bodySmall" color={error ? 'low' : 'textSecondary'}>{label}</Text>
      <View style={[styles.inputRow, { borderColor: lineColor, backgroundColor: colors.surface }]}>
        <TextInput value={value} onChangeText={onChange} keyboardType="decimal-pad" autoCorrect={false}
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          onSubmitEditing={onSubmit} returnKeyType="done" placeholder={hint} placeholderTextColor={colors.textMuted}
          accessibilityLabel={`${spoken}, in ${UNIT_WORDS[unit] ?? unit}`} {...fieldError(`${id}-error`, !!error)}
          style={[styles.input, { color: colors.textPrimary }]} />
        <Text variant="bodySmall" color="textMuted" aria-hidden>{unit}</Text>
      </View>
      {error ? (
        <LiveText error nativeID={`${id}-error`} variant="bodySmall" color="low" style={styles.error}>{error}</LiveText>
      ) : null}
    </View>
  );
}

export default function LogSweatScreen() {
  const api = useApi();
  const { workoutId } = useLocalSearchParams<{ workoutId: string }>();
  const key = useMemo(() => ({ api, workoutId }), [api, workoutId]);
  const base = useLoad(async () => {
    const [workout, settings, sweat] = await Promise.all([
      api.workout(workoutId),
      api.settings(),
      api.workoutSweat(workoutId).catch(() => null),
    ]);
    return { workoutId, workout, units: settings.units as Units, sweat };
  }, key);
  const [typed, setTyped] = useState<Record<AmountKind, string>>(EMPTY);
  const [errors, setErrors] = useState<Partial<Record<AmountKind, string>>>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // A ref, not state: two taps in the same moment both see state from before the first one.
  const busy = useRef(false);

  const current = base.data && base.data.workoutId === workoutId ? base.data : null;
  const before = current?.sweat?.source === 'manual' ? current.sweat : null;
  // Numbers typed in earlier fill the boxes, so saving again doesn't drop the optional ones by accident.
  // Filled once per load, while rendering (React's way to reset state when an input changes).
  const [filledFrom, setFilledFrom] = useState<typeof current>(null);
  if (current && filledFrom !== current) {
    setFilledFrom(current);
    setErrors({});
    setTyped(before ? {
      fluid: amountInput(before.fluid_loss_ml, 'fluid', current.units),
      sodium: amountInput(before.sodium_mg, 'sodium', current.units),
      rate: amountInput(before.sweat_rate_l_h, 'rate', current.units),
    } : EMPTY);
  }

  const home = { pathname: '/train/workout/[workoutId]' as const, params: { workoutId } };
  const header = (back: string, to: typeof home | '/train' = home) => (
    <SubPageHeader back={back} home={to} label="Sweat sensor" title="Log a sweat session"
      intro="Add the numbers from your sweat sensor after a workout." />
  );
  // Opened without a workout (an old link, say), so there's nothing to log against.
  if (!workoutId) {
    return (
      <Page>
        {/* Figma's no-workout frame: only the way back and what to do. */}
        <SubPageHeader back="Train" home="/train" label="Sweat sensor" />
        <Text variant="body" color="textSecondary">Open a workout first, then log its sweat session from there.</Text>
      </Page>
    );
  }
  if (!current) {
    return <Page>{header('Workout')}<PageState loading={base.loading || !!base.data} error={base.error} onRetry={base.reload} /></Page>;
  }
  const { workout, units } = current;

  async function save() {
    if (busy.current) return;
    const saved = { fluid: before?.fluid_loss_ml ?? null, sodium: before?.sodium_mg ?? null, rate: before?.sweat_rate_l_h ?? null };
    const parsed = FIELDS.map((f) => [f.kind, typedValue(typed[f.kind], f.kind, units, saved[f.kind])] as const);
    const bad = Object.fromEntries(parsed.flatMap(([k, r]) => ('error' in r ? [[k, r.error]] : [])));
    setErrors(bad);
    if (Object.keys(bad).length) return;
    const value = (k: AmountKind) => {
      const r = parsed.find(([kind]) => kind === k)![1];
      return 'value' in r ? r.value : null;
    };
    busy.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      await api.saveSweatManually(workout.id, {
        fluid_loss_ml: value('fluid')!,
        sodium_mg: value('sodium'),
        sweat_rate_l_h: value('rate'),
      });
      // Back to the workout, so Back from there goes to Train rather than to this form.
      if (router.canGoBack()) router.back();
      else router.replace(home);
    } catch (e) {
      setSaveError(`Couldn't save. ${errorText(e)}`);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  return (
    <Page form>
      {header(workout.type)}
      <Panel style={styles.panel}>
        <ListRow label="Workout" value={`${startLabel(workout.start_local).split(' · ')[0]} · ${workout.type}`} />
        <ListRow label="Import a Nix file" value=".xlsx"
          onPress={() => router.replace({ pathname: '/train/import', params: { workoutId } })} />
      </Panel>
      <View style={styles.form}>
        {FIELDS.map((f) => (
          <Field key={f.kind} id={`sweat-${f.kind}`} label={f.label} spoken={f.spoken} hint={amountHint(f.kind, units)}
            unit={amountUnit(f.kind, units)} value={typed[f.kind]} error={errors[f.kind] ?? null} onSubmit={save}
            onChange={(t) => setTyped((prev) => ({ ...prev, [f.kind]: t }))} />
        ))}
        <Text variant="bodySmall" color="textSecondary">Copy these from your sensor’s app after the workout.</Text>
        {saveError ? <LiveText error color="low">{saveError}</LiveText> : null}
        <Button title="Save session" busy={saving} onPress={save} />
        <Button title="Cancel" kind="secondary" disabled={saving}
          onPress={() => (router.canGoBack() ? router.back() : router.replace(home))} />
      </View>
    </Page>
  );
}

const styles = StyleSheet.create({
  panel: { maxWidth: 520 },
  form: { marginTop: 24, gap: 18, maxWidth: 520 },
  field: { gap: 6 },
  inputRow: { flexDirection: 'row', alignItems: 'center', borderWidth: 2, borderRadius: radius.sm, minHeight: 46,
    paddingHorizontal: 14, gap: 8 },
  // The teal or red outline is on the box around it. Chrome draws its own ring for the "auto" outline style
  // whatever its colour, so it's set to a solid ring 0 px wide instead.
  input: { ...type.body, flex: 1, minHeight: 44, paddingVertical: 8, outlineStyle: 'solid', outlineWidth: 0,
    borderWidth: 0, backgroundColor: 'transparent' },
  error: { marginTop: 4 },
});
