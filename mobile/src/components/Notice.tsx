import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, StyleSheet } from 'react-native';

import { announce } from '../lib/a11y';
import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Text } from './Text';

type Props = {
  /** Warning sits on an amber tint, Info on a teal one (Figma's Notice, Type = Warning / Info). */
  type: 'warning' | 'info';
  label: string;
  children: string;
  /** Read out when it appears, for notes that show up after something the person did (like picking a file). */
  live?: boolean;
};

/** A short note on a tinted panel: a small label on top, one or two lines of text below. */
export function Notice({ type, label, children, live }: Props) {
  const { colors } = useTheme();
  const tone = type === 'warning' ? 'moderate' : 'textPrimary';
  const spoken = `${label}. ${children}`;
  useEffect(() => {
    if (live) announce(spoken);
  }, [live, spoken]);
  // A notice that pops up slides down into place (motion spec). With reduced motion it only fades in.
  // shortcut: it doesn't slide out when it goes away, that needs the parent to keep it while it leaves.
  const [shown] = useState(() => new Animated.Value(live ? 0 : 1));
  const [slide, setSlide] = useState(true);
  useEffect(() => {
    if (!live) return;
    AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      setSlide(!reduce);
      Animated.timing(shown, { toValue: 1, duration: reduce ? 200 : 300, useNativeDriver: false }).start();
    });
  }, [live, shown]);
  const drop = shown.interpolate({ inputRange: [0, 1], outputRange: [slide ? -12 : 0, 0] });
  return (
    // Read as one piece, so a screen reader says the label and the text together.
    <Animated.View accessible accessibilityLabel={spoken} aria-live={live ? 'polite' : undefined}
      style={[styles.notice, { backgroundColor: type === 'warning' ? colors.warningTint : colors.infoTint,
        opacity: shown, transform: [{ translateY: drop }] }]}>
      <Text variant="labelSmall" color={tone}>{label}</Text>
      <Text variant="body" style={styles.text}>{children}</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  notice: { borderRadius: radius.md, padding: 16 },
  text: { marginTop: 4 },
});
