import { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Text } from '../../components/Text';
import { useTheme } from '../../theme/theme';

type Props = { label: string; selected: boolean; onPress: () => void; arrow?: boolean; children?: ReactNode };

/** One choice on the Update time screen. children open under the row (the "Other time" box). */
export function TimeRow({ label, selected, onPress, arrow, children }: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.rule, { borderTopColor: colors.border }]}>
      <Pressable onPress={onPress} accessibilityRole="radio" accessibilityState={{ checked: selected }} style={styles.row}>
        <Text variant="bodyEmphasis">{label}</Text>
        <View style={styles.marks}>
          {selected ? <Text variant="body" color="accent">Selected</Text> : null}
          {arrow ? <Text variant="body" color="textSecondary">→</Text> : null}
        </View>
      </Pressable>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  rule: { borderTopWidth: 1 },
  row: { minHeight: 51, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  marks: { flexDirection: 'row', gap: 10 },
});
