import { StyleSheet, View } from 'react-native';

import { Today } from '../../api/client';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { useTheme } from '../../theme/theme';
import { radius } from '../../theme/tokens';

// Figma's shorter names for the inputs. Anything new falls back to the server's label.
const NAMES: Record<string, string> = { hrv: 'HRV', rhr: 'Resting heart rate', sleep: 'Sleep',
  efficiency: 'Sleep efficiency', fragmentation: 'Awakenings' };

/** "−7 points", "+3 points", "0 points". */
export function pointsText(points: number): string {
  const n = Math.round(points);
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n)} ${Math.abs(n) === 1 ? 'point' : 'points'}`;
}

/** The line under the rows: why these inputs moved the score, or that nothing stood out. */
export function movedNote(t: Today): string {
  if (t.readiness?.confidence === 'sleep_only') return 'Only sleep counted today. HRV and resting heart rate were missing.';
  const compared = t.metrics.filter((m) => m.direction !== null);
  if (compared.length && compared.every((m) => m.direction === 'usual')) {
    return 'Nothing stood out. Every reading was inside your usual range.';
  }
  // With the score at the middle the points cancel out, so a list of zeros needs saying why.
  if ((t.readiness?.contributions ?? []).every((c) => Math.round(c.points) === 0)) {
    return 'The ups and downs evened out, so nothing moved the score much.';
  }
  return 'Points against a usual night.';
}

/** Today's "What moved your score": each input's points, from the readiness model's contributions. */
export function WhatMoved({ today: t }: { today: Today }) {
  const { colors } = useTheme();
  const rows = t.readiness?.contributions ?? [];
  if (!rows.length) return null;
  return (
    <View style={[styles.panel, { backgroundColor: colors.surface }]}>
      <SectionHeader title="What moved your score" />
      {rows.map((c) => {
        const tone = c.points <= -0.5 ? 'moderate' : c.points >= 0.5 ? 'ready' : 'textSecondary';
        return (
          // Read as one line: "HRV, minus 7 points".
          <View key={c.input} accessible style={styles.row}
            accessibilityLabel={`${NAMES[c.input] ?? c.label}, ${pointsText(c.points).replace('−', 'minus ').replace('+', 'plus ')}`}>
            <Text variant="body">{NAMES[c.input] ?? c.label}</Text>
            <Text variant="bodyEmphasis" color={tone}>{pointsText(c.points)}</Text>
          </View>
        );
      })}
      <Text variant="bodySmall" color="textSecondary" style={styles.note}>{movedNote(t)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { borderRadius: radius.lg, paddingHorizontal: 16, paddingBottom: 16 },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 6 },
  note: { marginTop: 8 },
});
