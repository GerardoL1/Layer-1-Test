import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import { announce } from '../lib/a11y';
import { useTheme } from '../theme/theme';
import { Text } from './Text';

type Props = {
  /** Warning has an amber bar, Info an accent one (Figma's Notice, Type = Warning / Info). */
  type: 'warning' | 'info';
  label: string;
  children: string;
  /** Read out when it appears, for notes that show up after something the person did (like picking a file). */
  live?: boolean;
};

/** A short note with a colored bar on its left: a small label on top, one or two lines of text below. */
export function Notice({ type, label, children, live }: Props) {
  const { colors } = useTheme();
  const tone = type === 'warning' ? 'moderate' : 'accent';
  const spoken = `${label}. ${children}`;
  useEffect(() => {
    if (live) announce(spoken);
  }, [live, spoken]);
  return (
    // Read as one piece, so a screen reader says the label and the text together.
    <View accessible accessibilityLabel={spoken} aria-live={live ? 'polite' : undefined}
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
