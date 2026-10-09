import { Pressable, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

type Props = {
  label: string;
  value?: string | null;
  /** Link rows get an arrow and open something when tapped. */
  onPress?: () => void;
  /** Shown greyed out with "Coming soon" instead of a value. Nothing happens on tap. */
  comingSoon?: boolean;
  /** Red label, for things like "Delete my data". */
  danger?: boolean;
  /** Color the value, e.g. green for "Connected". */
  valueColor?: 'ready' | 'low' | 'moderate';
};

/** Settings and info lines. Value shows a fact, Link adds an arrow and opens another screen. */
export function ListRow({ label, value, onPress, comingSoon, danger, valueColor }: Props) {
  const { colors } = useTheme();
  const link = !!onPress && !comingSoon;
  return (
    <Pressable onPress={link ? onPress : undefined} disabled={!link}
      accessibilityRole={link ? 'button' : undefined}
      accessibilityState={comingSoon ? { disabled: true } : undefined}
      accessibilityHint={comingSoon ? 'Coming soon' : undefined}
      style={({ pressed }) => ({ borderTopWidth: 1, borderTopColor: colors.border, minHeight: 51,
        flexDirection: 'row', alignItems: 'center', gap: 12, opacity: comingSoon ? 0.55 : pressed ? 0.7 : 1 })}>
      <Text variant="bodyLarge" color={danger ? 'low' : 'textPrimary'} style={{ flex: 1 }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexShrink: 1 }}>
        <Text variant="body" color={comingSoon ? 'textMuted' : valueColor ?? 'textSecondary'}
          numberOfLines={1} style={{ textAlign: 'right' }}>
          {comingSoon ? 'Coming soon' : value ?? ''}
        </Text>
        {link || (onPress && comingSoon) ? <Text variant="body" color="textSecondary">→</Text> : null}
      </View>
    </Pressable>
  );
}
