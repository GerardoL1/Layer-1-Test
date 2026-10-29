import { ActivityIndicator, Pressable, StyleProp, StyleSheet, ViewStyle } from 'react-native';

import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Text } from './Text';

type Props = {
  title: string;
  onPress?: () => void;
  /** text: no fill and no outline, for quieter actions like "Choose a different file". */
  kind?: 'primary' | 'secondary' | 'text';
  /** Figma's State = Disabled, for actions that aren't available (like "Coming soon"). */
  disabled?: boolean;
  busy?: boolean;
  style?: StyleProp<ViewStyle>;
};

/**
 * Primary = filled, secondary = outlined, both fully round. One primary per screen.
 * Disabled uses muted colors from Figma instead of fading, so it stays readable in both modes.
 */
export function Button({ title, onPress, kind = 'primary', disabled, busy, style }: Props) {
  const { colors } = useTheme();
  const primary = kind === 'primary';
  const look = primary
    ? disabled
      ? { fill: colors.surfaceMuted, border: colors.surfaceMuted, text: colors.textMuted }
      : { fill: colors.accent, border: colors.accent, text: colors.onAccent }
    : kind === 'text'
      ? { fill: 'transparent', border: 'transparent', text: disabled ? colors.textMuted : colors.textPrimary }
      : disabled
        ? { fill: 'transparent', border: colors.borderStrong, text: colors.textMuted }
        : { fill: 'transparent', border: colors.borderStrong, text: colors.textPrimary };
  const off = disabled || busy;
  return (
    // react-native-web sets aria-disabled from disabled, so both are given.
    <Pressable accessibilityRole="button" disabled={!!off} aria-disabled={!!off} aria-busy={!!busy}
      onPress={off ? undefined : onPress}
      // Reacts on press down, not release (motion spec). shortcut: snaps to 0.97 with no 100 ms ease, add one if it feels abrupt.
      style={({ pressed }) => [styles.button, { backgroundColor: look.fill, borderColor: look.border,
        transform: [{ scale: pressed && !off ? 0.97 : 1 }] }, style]}>
      {busy ? <ActivityIndicator color={look.text} />
        : <Text variant="button" style={{ color: look.text }}>{title}</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { minHeight: 46, paddingHorizontal: 18, borderRadius: radius.full, alignItems: 'center',
    justifyContent: 'center', borderWidth: 1 },
});
