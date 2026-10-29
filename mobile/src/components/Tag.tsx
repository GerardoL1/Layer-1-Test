import { StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Text } from './Text';

/** A small round label, like Sweat or Patch on a workout row, saying which extra data it has. */
export function Tag({ label }: { label: string }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.tag, { backgroundColor: colors.surface }]}>
      <Text variant="bodySmall" color="textSecondary">{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tag: { borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 3 },
});
