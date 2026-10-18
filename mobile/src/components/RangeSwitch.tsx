import { Pressable, StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

export type Range = 14 | 28 | 90;
const RANGES: Range[] = [14, 28, 90];

/** Chooses how many nights the Trends charts show. The chosen range is dark and underlined. */
export function RangeSwitch({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  const { colors } = useTheme();
  return (
    <View accessibilityRole="tablist" style={styles.tabs}>
      {RANGES.map((r) => {
        const on = r === value;
        return (
          <Pressable key={r} onPress={() => onChange(r)} accessibilityRole="tab" aria-selected={on}
            style={[styles.tab, { borderBottomColor: on ? colors.borderStrong : 'transparent' }]}>
            <Text variant="labelMedium" color={on ? 'textPrimary' : 'textMuted'}>{r} nights</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  tabs: { flexDirection: 'row', gap: 20 },
  tab: { paddingBottom: 5, borderBottomWidth: 2 },
});
