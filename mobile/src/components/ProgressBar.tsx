import { StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';

/** 4 px bar from Figma: muted track, primary text color fill. share is 0 to 1. */
export function ProgressBar({ share }: { share: number }) {
  const { colors } = useTheme();
  const pct = Math.round(Math.min(1, Math.max(0, share)) * 100);
  return (
    <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: pct }}
      style={[styles.bar, { backgroundColor: colors.surfaceMuted }]}>
      <View style={[styles.bar, { width: `${pct}%`, backgroundColor: colors.textPrimary }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { height: 4 },
});
