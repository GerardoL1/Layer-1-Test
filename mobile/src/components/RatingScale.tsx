import { Pressable, StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Text } from './Text';

const POINTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

/**
 * A 1 to 10 question from the check-ins (Figma "Rating option" row), with the words for each end under it.
 * Screen readers hear the end words on 1 and 10, since the row under them isn't tied to a number.
 */
export function RatingScale({ question, low, high, value, onPick, disabled }: {
  question: string; low: string; high: string; value: number | null | undefined; onPick: (n: number) => void;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <Text variant="bodyEmphasis">{question}</Text>
      <View accessibilityRole="radiogroup" accessibilityLabel={question} style={styles.row}>
        {POINTS.map((n) => {
          const on = n === value;
          return (
            <Pressable key={n} accessibilityRole="radio" aria-checked={on} disabled={disabled} onPress={() => onPick(n)}
              accessibilityLabel={n === 1 ? `1, ${low}` : n === 10 ? `10, ${high}` : String(n)}
              style={[styles.option, { backgroundColor: on ? colors.inverse : colors.surface }]}>
              <Text variant="body" style={{ color: on ? colors.canvas : colors.textPrimary }}>{n}</Text>
            </Pressable>
          );
        })}
      </View>
      <View style={styles.ends} aria-hidden>
        <Text variant="bodySmall" color="textSecondary">{low}</Text>
        <Text variant="bodySmall" color="textSecondary">{high}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12 },
  row: { flexDirection: 'row', gap: 4 },
  // Fills the iPhone width (about 32 wide) and stops at a 44 circle on a computer, like Figma.
  option: { flex: 1, maxWidth: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: radius.full },
  ends: { flexDirection: 'row', justifyContent: 'space-between', maxWidth: 476 },
});
