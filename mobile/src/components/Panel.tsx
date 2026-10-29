import { ReactNode } from 'react';
import { StyleProp, StyleSheet, View, ViewProps, ViewStyle } from 'react-native';

import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';

/** A group of rows on a tinted, rounded panel. The redesign groups rows this way instead of divider lines. */
export function Panel({ children, style, ...rest }: ViewProps & { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const { colors } = useTheme();
  return <View {...rest} style={[styles.panel, { backgroundColor: colors.surface }, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  panel: { borderRadius: radius.md, paddingHorizontal: 16, paddingVertical: 4 },
});
