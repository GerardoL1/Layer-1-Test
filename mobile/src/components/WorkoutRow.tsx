import { Pressable, StyleSheet, View } from 'react-native';

import { duration, durationWords, sourceText, startLabel } from '../lib/sweat';
import { useTheme } from '../theme/theme';
import { Tag } from './Tag';
import { Text } from './Text';

type Props = {
  startLocal: string;
  type: string;
  minutes: number;
  source: string;
  /** Which extra data the workout has, like ['SWEAT']. */
  tags: string[];
  onPress: () => void;
};

/** One workout in the Train tab and All workouts: when, what, how long, where from, and its data tags. */
export function WorkoutRow({ startLocal, type, minutes, source, tags, onPress }: Props) {
  const { colors } = useTheme();
  const when = startLabel(startLocal);
  const detail = `${duration(minutes)} · ${sourceText(source)}`;
  const spoken = [type, when, `${durationWords(minutes)}, ${sourceText(source)}`, tags.length ? `Has ${tags.join(' and ').toLowerCase()} data` : null]
    .filter(Boolean)
    .join('. ');
  return (
    <Pressable accessibilityRole="link" accessibilityLabel={spoken} onPress={onPress}
      style={({ pressed }) => [styles.row, { borderTopColor: colors.border, opacity: pressed ? 0.7 : 1 }]}>
      <View style={styles.text}>
        <Text variant="labelSmall" color="textSecondary">{when}</Text>
        <Text variant="bodyEmphasis" style={styles.type}>{type}</Text>
        <Text variant="bodySmall" color="textSecondary">{detail}</Text>
      </View>
      <View style={styles.right}>
        {tags.map((t) => <Tag key={t} label={t} />)}
        {/* The arrow is only a picture, so screen readers skip it. */}
        <Text variant="body" color="textSecondary" aria-hidden>→</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { minHeight: 66, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 12 },
  text: { flex: 1, gap: 2 },
  type: { marginTop: 2 },
  right: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' },
});
