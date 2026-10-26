import { Pressable, StyleSheet, View } from 'react-native';

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
  /** For rows that open an editor under themselves: whether it's open now. */
  expanded?: boolean;
  /** Color the value, e.g. green for "Connected". */
  valueColor?: 'ready' | 'low' | 'moderate';
  /** What tapping does, for screen readers, when the label alone doesn't say (like "Changes the workout"). */
  hint?: string;
};

/** Settings and info lines. Value shows a fact, Link adds an arrow and opens another screen. */
export function ListRow({ label, value, onPress, comingSoon, danger, valueColor, expanded, hint }: Props) {
  const { colors } = useTheme();
  const link = !!onPress && !comingSoon;
  const content = (
    <>
      <Text variant="bodyLarge" color={danger ? 'low' : 'textPrimary'} style={styles.label}>{label}</Text>
      <View style={styles.right}>
        <Text variant="body" color={comingSoon ? 'textMuted' : valueColor ?? 'textSecondary'} style={styles.value}>
          {comingSoon ? 'Coming soon' : value ?? ''}
        </Text>
        {/* The arrow is only a picture, so screen readers skip it. */}
        {link || (onPress && comingSoon) ? <Text variant="body" color="textSecondary" aria-hidden>→</Text> : null}
      </View>
    </>
  );
  // A row that only shows a fact is a plain View. As a Pressable the web would call it disabled.
  if (!onPress) return <View style={[styles.row, { borderTopColor: colors.border }]}>{content}</View>;
  return (
    <Pressable onPress={link ? onPress : undefined} disabled={!link}
      accessibilityRole="button" aria-disabled={comingSoon || undefined} aria-expanded={expanded}
      accessibilityHint={comingSoon ? 'Coming soon' : hint}
      style={({ pressed }) => [styles.row, { borderTopColor: colors.border,
        opacity: comingSoon ? 0.55 : pressed ? 0.7 : 1 }]}>
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { borderTopWidth: 1, minHeight: 51, flexDirection: 'row', alignItems: 'center', gap: 12 },
  label: { flex: 1 },
  right: { flexDirection: 'row', alignItems: 'center', gap: 10, flexShrink: 1, paddingVertical: 8 },
  value: { textAlign: 'right' },
});
