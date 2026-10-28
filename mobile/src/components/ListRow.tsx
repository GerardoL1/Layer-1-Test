import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
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
      {/* The label keeps its line, the value takes what's left and wraps if it has to. */}
      <Text variant="bodyEmphasis" color={danger ? 'low' : 'textPrimary'} style={value || comingSoon ? styles.label : styles.only}>{label}</Text>
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
  if (!onPress) return <View style={styles.row}>{content}</View>;
  return (
    <Pressable onPress={link ? onPress : undefined} disabled={!link}
      accessibilityRole="button" aria-disabled={comingSoon || undefined} aria-expanded={expanded}
      accessibilityHint={comingSoon ? 'Coming soon' : hint}
      // The web drops accessibilityHint, so there the hint joins the label. Rows without one are left alone.
      accessibilityLabel={Platform.OS === 'web' && hint && !comingSoon ? [label, value, hint].filter(Boolean).join(', ') : undefined}
      // Rows darken on press down (motion spec).
      style={({ pressed }) => [styles.row, { opacity: comingSoon ? 0.55 : 1,
        backgroundColor: pressed && link ? colors.surface : 'transparent' }]}>
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { minHeight: 51, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: radius.md },
  label: { flexShrink: 0 },
  only: { flex: 1 },
  right: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 10, flex: 1,
    paddingVertical: 8 },
  value: { textAlign: 'right', flexShrink: 1 },
});
