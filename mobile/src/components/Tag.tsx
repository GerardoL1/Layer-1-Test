import { StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Text } from './Text';

/** A small outlined label, like SWEAT or PATCH on a workout row, saying which extra data it has. */
export function Tag({ label }: { label: string }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.tag, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <Text variant="labelSmall" color="textSecondary">{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tag: { borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 3 },
});
