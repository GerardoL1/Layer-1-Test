import { StyleSheet, View } from 'react-native';

import { Direction } from '../api/client';
import { useTheme } from '../theme/theme';
import { Text } from './Text';

type Props = {
  label: string;
  /** Used on the narrowest phones, e.g. "Resting HR". */
  shortLabel?: string;
  value: string;
  unit?: string;
  /** Change against your usual, e.g. "-18%" or "+5 bpm". "usual" when within the usual range. */
  delta?: string | null;
  direction: Direction;
};

const SPOKEN: Partial<Record<NonNullable<Direction>, string>> = {
  worse: 'worse than usual',
  better: 'better than usual',
  usual: 'within your usual',
};

/** "+5 bpm" -> "▲ +5 bpm". Words like "Usual" or "More" are left alone. */
function withArrow(delta: string): string {
  if (delta.startsWith('+')) return `▲ ${delta}`;
  if (delta.startsWith('−') || delta.startsWith('-')) return `▼ ${delta}`;
  return delta;
}

/**
 * One line of the "Last night" table: measure, value, and change against your usual.
 * Color says better or worse, so the arrow and the spoken words carry it too for anyone who can't see the color.
 */
export function MetricRow({ label, shortLabel, value, unit, delta, direction }: Props) {
  const { colors, isNarrow } = useTheme();
  const deltaColor = direction === 'worse' ? colors.low : direction === 'better' ? colors.ready : colors.textMuted;
  const judged = direction ? SPOKEN[direction] : undefined;
  // A change of zero ("0 bpm") sounds odd read aloud.
  const change = delta && /^[+−-]?0(\D|$)/.test(delta) ? 'no change' : delta;
  const spoken = [`${label}: ${value} ${unit ?? ''}`.trim(), change, judged].filter(Boolean).join(', ');
  return (
    <View accessible role="group" accessibilityLabel={spoken} style={[styles.row, { borderTopColor: colors.border }]}>
      {/* The row's label says it all, so the parts aren't read again one by one on the web. */}
      <View aria-hidden style={styles.parts}>
        <Text variant="bodyLarge" style={styles.label}>{isNarrow && shortLabel ? shortLabel : label}</Text>
        <View style={styles.reading}>
          <Text variant="scoreMetric">{value}</Text>
          <Text variant="bodySmall" color="textMuted" style={styles.unit}>{unit ?? ''}</Text>
        </View>
        <Text variant="labelSmall" style={[styles.delta, { minWidth: isNarrow ? 70 : 84, color: deltaColor }]}>
          {delta ? withArrow(delta) : ''}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { borderTopWidth: 1, minHeight: 58, justifyContent: 'center' },
  parts: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', paddingVertical: 6 },
  label: { flex: 1, minWidth: 120 },
  reading: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'flex-end', minWidth: 96 },
  unit: { marginLeft: 4, minWidth: 28 },
  delta: { textAlign: 'right' },
});
