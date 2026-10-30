/**
 * Train > a workout: its length and its sweat data (Layer 3), with the rehydrate advice.
 * The patch parts of Figma's "Workout summary" (fatigue by set, muscles worked) come with Layer 2.
 */
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useMemo } from 'react';
import { StyleSheet, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { ListRow } from '../../components/ListRow';
import { LiveText } from '../../components/LiveText';
import { Notice } from '../../components/Notice';
import { Page, PageState } from '../../components/Page';
import { Panel } from '../../components/Panel';
import { SectionHeader } from '../../components/SectionHeader';
import { SubPageHeader } from '../../components/SubPageHeader';
import { Text } from '../../components/Text';
import { ratingText } from '../../lib/checkin';
import { about, duration, durationWords, sessionStats, Shown, sourceText, spanLabel, Units } from '../../lib/sweat';
import { errorText, useLoad } from '../../lib/useLoad';
import { Colors } from '../../theme/tokens';
import { RefreshError } from './RefreshError';

const NO_SWEAT = "Nix didn't pick up any sweat this session. Only breathing loss was recorded, so this won't count "
  + 'as sweat data.';
const UNIT_WORDS: Record<string, string> = { ml: 'millilitres', L: 'litres', oz: 'ounces', 'L/h': 'litres an hour',
  'oz/h': 'ounces an hour', mg: 'milligrams' };

type StatProps = { label: string; shown: Shown | null; color?: keyof Colors; spoken?: string; big?: boolean };

/** A small label over a figure, like "Fluid lost 1.4 L". Read out as one phrase. */
function Stat({ label, shown, color = 'textPrimary', spoken, big }: StatProps) {
  const said = spoken ?? (shown && shown.unit ? `${shown.value} ${UNIT_WORDS[shown.unit] ?? shown.unit}` : 'not measured');
  return (
    <View accessible accessibilityLabel={`${label}: ${said}`} style={styles.stat}>
      <Text variant="bodySmall" color="textSecondary">{label}</Text>
      {/* Duration reads "35 min" at full size. Sweat figures keep their unit small, like Figma. */}
      <Text variant="scoreMetric" color={color}>
        {shown ? shown.value : '–'}
        {shown?.unit ? <Text variant={big ? 'scoreMetric' : 'bodySmall'} color={big ? color : 'textSecondary'}>{` ${shown.unit}`}</Text> : null}
      </Text>
    </View>
  );
}

export default function WorkoutScreen() {
  const api = useApi();
  const { workoutId } = useLocalSearchParams<{ workoutId: string }>();
  // Load again when the tester or the workout changes.
  const key = useMemo(() => ({ api, workoutId }), [api, workoutId]);
  const { data, loading, error, reload } = useLoad(async () => {
    // Sweat data failing on its own shouldn't hide the workout, so its error is kept separately.
    const sweatLoad = api.workoutSweat(workoutId).then(
      (sweat) => ({ sweat, sweatError: null }),
      (e) => ({ sweat: null, sweatError: errorText(e) }),
    );
    const [workout, settings, { sweat, sweatError }] = await Promise.all([
      api.workout(workoutId),
      api.settings(),
      sweatLoad,
    ]);
    return { workoutId, workout, sweat, sweatError, units: settings.units as Units };
  }, key);
  // The check-in saves with Back, so the summary loads again whenever it's shown, or the row keeps the old value.
  useFocusEffect(useCallback(() => reload(), [reload]));

  // Old data from another workout is never shown under this one's address.
  const current = data && data.workoutId === workoutId ? data : null;
  if (!current) {
    return (
      <Page>
        <SubPageHeader back="Train" home="/train" label="Workout" title="Workout" />
        <PageState loading={loading || !!data} error={error} onRetry={reload} />
      </Page>
    );
  }
  const { workout: w, sweat: s, sweatError, units } = current;
  const mins = duration(w.duration_min).split(' ');
  const otherWarnings = s ? s.warnings.filter((x) => !x.startsWith("Nix didn't pick up any sweat")) : [];
  const rehydrate = s && s.rehydrate_ml !== null ? about(s.rehydrate_ml, units) : null;

  return (
    <Page>
      <View style={styles.column}>
        <SubPageHeader back="Train" home="/train" label="Workout" title={w.type}
          detail={`${spanLabel(w.start_local, w.end_local)} · ${sourceText(w.source)}`} />
        <RefreshError error={error} />
        {/* In a row like the sweat figures, since the stat's flex sizing is meant for a row. */}
        <View style={styles.statsRow}>
          <Stat label="Duration" shown={{ value: mins.slice(0, -1).join(' '), unit: mins[mins.length - 1] }}
            spoken={durationWords(w.duration_min)} big />
        </View>
        {/* The after-workout check-in. Shown here only, not on the workout lists. */}
        <Panel style={styles.space16}>
          <ListRow label="How was it?" value={ratingText(w)}
            onPress={() => router.push({ pathname: '/train/workout/[workoutId]/rate', params: { workoutId: w.id } })} />
        </Panel>

        <View style={styles.space32}>
          <SectionHeader title="Sweat" note={s ? (s.source === 'nix' ? 'From Nix' : 'Typed in') : null} />
          {sweatError ? (
            <LiveText error variant="body" color="low">{`Couldn't load the sweat data. ${sweatError}`}</LiveText>
          ) : s ? (
            <View style={styles.statsRow}>
              {sessionStats(s, units).map((x) => (
                <Stat key={x.label} label={x.label} shown={x.shown} color={x.tone === 'sweat' ? 'textPrimary' : 'textSecondary'} />
              ))}
            </View>
          ) : null}
          {/* Not offered when loading the sweat data failed: there may be data, and adding could replace it unseen.
              Breathing-only isn't sweat data, so it gets "Add" too. */}
          {sweatError ? null : (
            <Button title={s?.sweat_detected ? 'Update sweat data' : 'Add sweat data'} kind={s?.sweat_detected ? 'secondary' : 'primary'}
              style={styles.space16}
              onPress={() => router.push({ pathname: '/train/import', params: { workoutId: w.id } })} />
          )}
        </View>

        {s && !sweatError ? (
          <View style={styles.advice}>
            {!s.sweat_detected ? <Notice type="warning" label="No sweat picked up">{NO_SWEAT}</Notice> : null}
            {otherWarnings.map((x, i) => <Notice key={`${i}-${x}`} type="info" label="Check the numbers">{x}</Notice>)}
            {rehydrate ? (
              <View>
                <Text variant="bodySmall" color="textSecondary">Rehydrate</Text>
                <Text variant="body" style={styles.adviceText}>
                  {`Over the next few hours, drink about one and a half times what you lost (${rehydrate}), `
                    + 'with some salt: a salty snack or an electrolyte drink.'}
                </Text>
              </View>
            ) : null}
            <Text variant="bodySmall" color="textSecondary">
              Sweat numbers are estimates from the sensor. The advice is a placeholder until the team decides it.
            </Text>
          </View>
        ) : null}
      </View>
    </Page>
  );
}

const styles = StyleSheet.create({
  // Figma keeps the summary in one column on the computer too.
  column: { maxWidth: 520 },
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 16, marginTop: 4 },
  stat: { minWidth: 88, flexGrow: 1, flexBasis: 0, gap: 2 },
  advice: { marginTop: 20, gap: 14 },
  adviceText: { marginTop: 4 },
  space16: { marginTop: 16 },
  space32: { marginTop: 32 },
});
