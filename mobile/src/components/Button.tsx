import { ActivityIndicator, Pressable, ViewStyle } from 'react-native';

import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Text } from './Text';

type Props = {
  title: string;
  onPress?: () => void;
  kind?: 'primary' | 'secondary';
  disabled?: boolean;
  busy?: boolean;
  style?: ViewStyle;
};

/** Primary = filled accent. Secondary = text on a strong outline. */
export function Button({ title, onPress, kind = 'primary', disabled, busy, style }: Props) {
  const { colors } = useTheme();
  const primary = kind === 'primary';
  const off = disabled || busy;
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ disabled: !!off, busy: !!busy }}
      onPress={off ? undefined : onPress}
      style={({ pressed }) => [{
        minHeight: 46, paddingHorizontal: 20, borderRadius: radius.sm, alignItems: 'center',
        justifyContent: 'center', borderWidth: 1,
        backgroundColor: primary ? colors.accent : 'transparent',
        borderColor: primary ? colors.accent : colors.borderStrong,
        opacity: off ? 0.5 : pressed ? 0.85 : 1,
      }, style]}>
      {busy ? <ActivityIndicator color={primary ? colors.onAccent : colors.textPrimary} />
        : <Text variant="button" style={{ color: primary ? colors.onAccent : colors.textPrimary }}>{title}</Text>}
    </Pressable>
  );
}
