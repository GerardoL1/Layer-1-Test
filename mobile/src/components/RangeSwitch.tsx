import { Pressable, StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Text } from './Text';

export type Range = 14 | 28 | 90;
const RANGES: Range[] = [14, 28, 90];

/** Chooses how many nights the Trends charts show. A segmented control: the chosen range sits on a raised pill. */
export function RangeSwitch({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  const { colors } = useTheme();
  return (
    <View accessibilityRole="tablist" style={[styles.tabs, { backgroundColor: colors.surface }]}>
      {RANGES.map((r) => {
        const on = r === value;
        return (
          <Pressable key={r} onPress={() => onChange(r)} accessibilityRole="tab" aria-selected={on}
            style={[styles.tab, on && { backgroundColor: colors.raised }]}>
            <Text variant={on ? 'labelMedium' : 'bodySmall'} color={on ? 'textPrimary' : 'textSecondary'}>{r} nights</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  tabs: { flexDirection: 'row', alignSelf: 'flex-start', padding: 4, gap: 4, borderRadius: radius.full },
  tab: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 16, borderRadius: radius.full },
});
