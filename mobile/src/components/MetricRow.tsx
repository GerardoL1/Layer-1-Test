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

/** One line of the "Last night" table: measure, value, and change against your usual. */
export function MetricRow({ label, shortLabel, value, unit, delta, direction }: Props) {
  const { colors, isNarrow } = useTheme();
  const deltaColor = direction === 'worse' ? colors.low : direction === 'better' ? colors.ready : colors.textMuted;
  return (
    <View accessible accessibilityLabel={`${label}: ${value} ${unit ?? ''}${delta ? `, ${delta}` : ''}`}
      style={[styles.row, { borderTopColor: colors.border }]}>
      <Text variant="bodyLarge" style={styles.label}>{isNarrow && shortLabel ? shortLabel : label}</Text>
      <View style={styles.reading}>
        <Text variant="scoreMetric">{value}</Text>
        <Text variant="bodySmall" color="textMuted" numberOfLines={1} style={styles.unit}>
          {unit ?? ''}
        </Text>
      </View>
      <Text variant="labelSmall" style={[styles.delta, { width: isNarrow ? 70 : 84, color: deltaColor }]}>
        {delta ?? ''}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { borderTopWidth: 1, minHeight: 58, flexDirection: 'row', alignItems: 'center' },
  label: { flex: 1 },
  reading: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'flex-end', minWidth: 96 },
  unit: { marginLeft: 4, width: 28 },
  delta: { textAlign: 'right' },
});
