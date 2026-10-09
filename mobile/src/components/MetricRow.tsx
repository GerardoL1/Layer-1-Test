import { View } from 'react-native';

import { Direction } from '../api/client';
import { useTheme } from '../theme/theme';
import { Text } from './Text';

type Props = {
  label: string;
  value: string;
  unit?: string;
  /** Change against your usual, e.g. "-18%" or "+5 bpm". "usual" when within the usual range. */
  delta?: string | null;
  direction: Direction;
};

/** One line of the "Last night" table: measure, value, and change against your usual. */
export function MetricRow({ label, value, unit, delta, direction }: Props) {
  const { colors } = useTheme();
  const deltaColor = direction === 'worse' ? colors.low : direction === 'better' ? colors.ready : colors.textMuted;
  return (
    <View accessible accessibilityLabel={`${label}: ${value} ${unit ?? ''}${delta ? `, ${delta}` : ''}`}
      style={{ borderTopWidth: 1, borderTopColor: colors.border, minHeight: 58, flexDirection: 'row',
        alignItems: 'center' }}>
      <Text variant="bodyLarge" style={{ flex: 1 }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'flex-end', minWidth: 96 }}>
        <Text variant="scoreMetric">{value}</Text>
        <Text variant="bodySmall" color="textMuted" numberOfLines={1} style={{ marginLeft: 4, width: 28 }}>
          {unit ?? ''}
        </Text>
      </View>
      <Text variant="labelSmall" style={{ width: 84, textAlign: 'right', color: deltaColor }}>
        {delta ?? ''}
      </Text>
    </View>
  );
}
