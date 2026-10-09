import { Pressable, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

export type Range = 14 | 28 | 90;
const RANGES: Range[] = [14, 28, 90];

/** Chooses how many nights the Trends charts show. The chosen range is dark and underlined. */
export function RangeSwitch({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  const { colors } = useTheme();
  return (
    <View accessibilityRole="tablist" style={{ flexDirection: 'row', gap: 20 }}>
      {RANGES.map((r) => {
        const on = r === value;
        return (
          <Pressable key={r} onPress={() => onChange(r)} accessibilityRole="tab" accessibilityState={{ selected: on }}
            style={{ paddingBottom: 5, borderBottomWidth: 2, borderBottomColor: on ? colors.borderStrong : 'transparent' }}>
            <Text variant="labelMedium" color={on ? 'textPrimary' : 'textMuted'}>{r} nights</Text>
          </Pressable>
        );
      })}
    </View>
  );
}
