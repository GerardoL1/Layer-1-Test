import { StyleSheet, View } from 'react-native';

import { MetricRow, Today } from '../../api/client';
import { Text } from '../../components/Text';
import { durationText, num } from '../../lib/format';
import { useTheme } from '../../theme/theme';
import { radius } from '../../theme/tokens';

const TILES: { key: string; label: string }[] = [
  { key: 'hrv', label: 'HRV' },
  { key: 'rhr', label: 'Resting HR' },
  { key: 'sleep', label: 'Sleep' },
  { key: 'awakenings', label: 'Awakenings' },
];

/** "6 h 3 m" for sleep, the plain number and its unit for the rest. */
function figure(m: MetricRow): { value: string; unit: string } {
  if (m.key === 'sleep') {
    if (m.value === null) return { value: '–', unit: '' };
    const total = Math.round(m.value);
    return { value: `${Math.floor(total / 60)} h ${total % 60} m`, unit: '' };
  }
  // No unit next to a missing value, so it reads "–" and not "– ms".
  if (m.value === null) return { value: num(m.value), unit: '' };
  return { value: num(m.value), unit: m.key === 'hrv' ? 'ms' : m.key === 'rhr' ? 'bpm' : '' };
}

/** How last night compares with the usual, in words: "18% below usual", "52 min short", "Usual for you". */
export function changeText(m: MetricRow): string {
  // No value: the watch didn't record it (the score is then based on what was). No direction: nothing to compare with.
  if (m.value === null) return 'Not recorded';
  if (m.direction === null) return 'Not compared';
  if (m.key === 'awakenings') {
    return m.direction === 'usual' ? 'Usual for you' : m.direction === 'worse' ? 'More than usual' : 'Fewer than usual';
  }
  const mean = m.usual_mean;
  if (m.value === null || mean === null || mean === 0) return 'Not compared';
  const diff = m.value - mean;
  if (m.key === 'hrv') {
    const pct = Math.abs(Math.round((diff / mean) * 100));
    return pct === 0 ? 'Same as usual' : `${pct}% ${diff < 0 ? 'below' : 'above'} usual`;
  }
  if (m.key === 'rhr') {
    const n = Math.abs(Math.round(diff));
    return n === 0 ? 'Same as usual' : `${n} ${diff < 0 ? 'below' : 'above'} usual`;
  }
  const n = Math.abs(Math.round(diff));
  return n === 0 ? 'Same as usual' : `${durationText(n)} ${diff < 0 ? 'short' : 'more'}`;
}

/** Last night's four figures as tiles: two by two on a phone, one row on a computer. */
export function LastNight({ today: t }: { today: Today }) {
  const { colors, isWide } = useTheme();
  const tiles = TILES.flatMap(({ key, label }) => {
    const m = t.metrics.find((x) => x.key === key);
    return m ? [{ m, label }] : [];
  });
  return (
    <View>
      <View style={styles.grid}>
        {tiles.map(({ m, label }) => {
          const f = figure(m);
          const change = changeText(m);
          const tone = m.direction === 'worse' ? 'moderate' : m.direction === 'better' ? 'ready' : 'textSecondary';
          return (
            // Read as one line: "HRV, 33 ms, 18% below usual".
            <View key={m.key} accessible accessibilityLabel={`${label}, ${f.value} ${f.unit}, ${change}`}
              style={[styles.tile, isWide ? styles.tileWide : styles.tilePhone, { backgroundColor: colors.surface }]}>
              <Text variant="bodySmall" color="textSecondary">{label}</Text>
              <View style={styles.figure}>
                <Text variant="scoreMetric">{f.value}</Text>
                {f.unit ? <Text variant="bodySmall" color="textSecondary">{f.unit}</Text> : null}
              </View>
              <Text variant="labelSmall" color={tone}>{change}</Text>
            </View>
          );
        })}
      </View>
      {t.quality_notes ? <Text variant="bodySmall" color="textMuted" style={styles.note}>Note: {t.quality_notes}.</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  tile: { borderRadius: radius.lg, padding: 16, gap: 4 },
  tilePhone: { flexBasis: '47%', flexGrow: 1 },
  tileWide: { flexBasis: '22%', flexGrow: 1 },
  figure: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  note: { marginTop: 8 },
});
