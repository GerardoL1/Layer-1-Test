import { ActivityIndicator, Pressable, StyleProp, StyleSheet, ViewStyle } from 'react-native';

import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Text } from './Text';

type Props = {
  title: string;
  onPress?: () => void;
  kind?: 'primary' | 'secondary';
  /** Figma's State = Disabled, for actions that aren't available (like "Coming soon"). */
  disabled?: boolean;
  busy?: boolean;
  style?: StyleProp<ViewStyle>;
};

/**
 * Primary = filled accent. Secondary = text on a strong outline.
 * Disabled uses muted colors from Figma instead of fading, so it stays readable in both modes.
 */
export function Button({ title, onPress, kind = 'primary', disabled, busy, style }: Props) {
  const { colors } = useTheme();
  const primary = kind === 'primary';
  const look = primary
    ? disabled
      ? { fill: colors.surfaceMuted, border: colors.surfaceMuted, text: colors.textMuted }
      : { fill: colors.accent, border: colors.accent, text: colors.onAccent }
    : disabled
      ? { fill: 'transparent', border: colors.border, text: colors.textMuted }
      : { fill: 'transparent', border: colors.borderStrong, text: colors.textPrimary };
  const off = disabled || busy;
  return (
    // react-native-web sets aria-disabled from disabled, so both are given.
    <Pressable accessibilityRole="button" disabled={!!off} aria-disabled={!!off} aria-busy={!!busy}
      onPress={off ? undefined : onPress}
      style={({ pressed }) => [styles.button, { backgroundColor: look.fill, borderColor: look.border,
        opacity: pressed && !off ? 0.85 : 1 }, style]}>
      {busy ? <ActivityIndicator color={look.text} />
        : <Text variant="button" style={{ color: look.text }}>{title}</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { minHeight: 46, paddingHorizontal: 18, borderRadius: radius.sm, alignItems: 'center',
    justifyContent: 'center', borderWidth: 1 },
});
