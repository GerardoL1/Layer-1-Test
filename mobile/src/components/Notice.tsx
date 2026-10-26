import { StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

type Props = {
  /** Warning has an amber bar, Info an accent one (Figma's Notice, Type = Warning / Info). */
  type: 'warning' | 'info';
  label: string;
  children: string;
};

/** A short note with a colored bar on its left: a small label on top, one or two lines of text below. */
export function Notice({ type, label, children }: Props) {
  const { colors } = useTheme();
  const tone = type === 'warning' ? 'moderate' : 'accent';
  return (
    // Read as one piece, so a screen reader says the label and the text together.
    <View accessible accessibilityLabel={`${label}. ${children}`}
      style={[styles.notice, { borderLeftColor: colors[tone] }]}>
      <Text variant="labelSmall" color={tone}>{label}</Text>
      <Text variant="body" style={styles.text}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  notice: { borderLeftWidth: 3, paddingLeft: 12, paddingVertical: 4 },
  text: { marginTop: 4 },
});
