/**
 * Train > a workout: its length and its sweat data (Layer 3), with the rehydrate advice.
 * The patch parts of Figma's "Workout summary" (fatigue by set, muscles worked) come with Layer 2.
 */
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { LiveText } from '../../components/LiveText';
import { Notice } from '../../components/Notice';
import { Page, PageState } from '../../components/Page';
import { SectionHeader } from '../../components/SectionHeader';
import { SubPageHeader } from '../../components/SubPageHeader';
import { Text } from '../../components/Text';
import { about, duration, durationWords, sessionStats, Shown, spanLabel, Units } from '../../lib/sweat';
import { errorText, useLoad } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';
import { Colors } from '../../theme/tokens';
import { RefreshError } from './RefreshError';

const NO_SWEAT = "Nix didn't pick up any sweat this session. Only breathing loss was recorded, so this won't count "
  + 'as sweat data.';
const UNIT_WORDS: Record<string, string> = { ml: 'millilitres', L: 'litres', oz: 'ounces', 'L/h': 'litres an hour',
  'oz/h': 'ounces an hour', mg: 'milligrams' };

type StatProps = { label: string; shown: Shown | null; color?: keyof Colors; spoken?: string };

/** A small label over a big number, like FLUID LOST 1.4 L. Read out as one phrase. */
function Stat({ label, shown, color = 'textPrimary', spoken }: StatProps) {
  const said = spoken ?? (shown && shown.unit ? `${shown.value} ${UNIT_WORDS[shown.unit] ?? shown.unit}` : 'not measured');
  return (
    <View accessible accessibilityLabel={`${label}: ${said}`} style={styles.stat}>
      <Text variant="labelSmall" color="textSecondary">{label}</Text>
      <View style={styles.statValue}>
        <Text variant="scoreMetric" color={color}>{shown ? shown.value : '–'}</Text>
        {shown?.unit ? <Text variant="bodySmall" color="textSecondary">{shown.unit}</Text> : null}
      </View>
    </View>
  );
}

export default function WorkoutScreen() {
  const api = useApi();
  const { colors, isWide } = useTheme();
  const { workoutId } = useLocalSearchParams<{ workoutId: string }>();
  // Load again when the tester or the workout changes.
  const key = useMemo(() => ({ api, workoutId }), [api, workoutId]);
  const { data, loading, error } = useLoad(async () => {
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

  // Old data from another workout is never shown under this one's address.
  const current = data && data.workoutId === workoutId ? data : null;
  if (!current) {
    return (
      <Page>
        <SubPageHeader back="Train" home="/train" label="Workout" title="Workout" />
        <PageState loading={loading || !!data} error={error} />
      </Page>
    );
  }
  const { workout: w, sweat: s, sweatError, units } = current;
  const mins = duration(w.duration_min).split(' ');

  const header = (
    <>
      <SubPageHeader back="Train" home="/train" label={spanLabel(w.start_local, w.end_local)} title={w.type} />
      <RefreshError error={error} />
    </>
  );
  const stats = (
    <View style={[styles.statsRow, styles.ruled, { borderTopColor: colors.borderStrong }]}>
      <Stat label="Duration" shown={{ value: mins.slice(0, -1).join(' '), unit: mins[mins.length - 1] }}
        spoken={durationWords(w.duration_min)} />
    </View>
  );

  const numbers = s ? (
    <View style={styles.statsRow}>
      {sessionStats(s, units).map((x) => (
        <Stat key={x.label} label={x.label} shown={x.shown} color={x.tone === 'sweat' ? 'sweat' : 'textSecondary'} />
      ))}
    </View>
  ) : null;

  const otherWarnings = s ? s.warnings.filter((x) => !x.startsWith("Nix didn't pick up any sweat")) : [];
  const rehydrate = s && s.rehydrate_ml !== null ? about(s.rehydrate_ml, units) : null;
  const advice = s ? (
    <View style={[styles.advice, { borderTopColor: colors.border }]}>
      {!s.sweat_detected ? <Notice type="warning" label="No sweat picked up">{NO_SWEAT}</Notice> : null}
      {otherWarnings.map((x, i) => <Notice key={`${i}-${x}`} type="info" label="Check the numbers">{x}</Notice>)}
      {rehydrate ? (
        <View>
          <Text variant="labelSmall" color="textSecondary">Rehydrate</Text>
          <Text variant="bodyLarge" style={styles.adviceText}>
            {`Over the next few hours, drink about one and a half times what you lost (${rehydrate}), `
              + 'with some salt: a salty snack or an electrolyte drink.'}
          </Text>
        </View>
      ) : null}
      <Text variant="bodySmall" color="textMuted">
        Sweat numbers are estimates from the sensor. The advice is a placeholder until the team decides it.
      </Text>
    </View>
  ) : null;

  const sweatBlock = (
    <View style={styles.space24}>
      <SectionHeader title="Sweat" note={s ? (s.source === 'nix' ? 'From Nix' : 'Typed in') : null} />
      {sweatError ? (
        <LiveText error variant="body" color="low">{`Couldn't load the sweat data. ${sweatError}`}</LiveText>
      ) : s ? numbers : (
        <Text variant="body" color="textSecondary">No sweat data for this workout yet.</Text>
      )}
      {/* Not offered when loading the sweat data failed: there may be data, and adding could replace it unseen. */}
      {sweatError ? null : (
        <Button title={s ? 'Update sweat data' : 'Add sweat data'} kind={s ? 'secondary' : 'primary'}
          style={styles.space16}
          onPress={() => router.push({ pathname: '/train/import', params: { workoutId: w.id } })} />
      )}
    </View>
  );

  if (isWide) {
    return (
      <Page>
        {header}
        <View style={styles.columns}>
          <View style={styles.column}>{stats}{sweatBlock}</View>
          <View style={[styles.column, styles.rightColumn]}>{advice}</View>
        </View>
      </Page>
    );
  }
  return (
    <Page>
      {header}
      {stats}
      {sweatBlock}
      {advice}
    </Page>
  );
}

const styles = StyleSheet.create({
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 16, paddingVertical: 14 },
  // The Sweat heading below brings its own rule, so the duration row only needs one on top.
  ruled: { borderTopWidth: 1 },
  stat: { minWidth: 96, flexGrow: 1, flexBasis: 0, gap: 4 },
  statValue: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  advice: { borderTopWidth: 1, paddingTop: 14, gap: 14 },
  adviceText: { marginTop: 6 },
  space16: { marginTop: 16 },
  space24: { marginTop: 24 },
  columns: { flexDirection: 'row', gap: 56 },
  column: { flex: 1 },
  rightColumn: { paddingTop: 88 },
});
