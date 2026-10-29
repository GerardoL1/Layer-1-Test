import { StyleSheet, View } from 'react-native';

import { Today } from '../../api/client';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { duration, fluid, joined, sodium } from '../../lib/sweat';
import { useTheme } from '../../theme/theme';
import { radius } from '../../theme/tokens';

/** Today's "Yesterday's run": the sweaty workout behind this morning's drink advice. Only when there is one. */
export function YesterdaysRun({ today: t }: { today: Today }) {
  const { colors } = useTheme();
  const h = t.hydration;
  if (!h) return null;
  const figures = [
    { label: 'Sweat lost', shown: fluid(h.fluid_ml, h.units) },
    ...(h.sodium_mg !== null ? [{ label: 'Sodium lost', shown: sodium(h.sodium_mg) }] : []),
    { label: 'Duration', shown: { value: String(Math.round(h.duration_min)), unit: 'min' } },
  ];
  // Long workouts read "1 h 10 min", which doesn't split into a number and a unit.
  if (h.duration_min >= 60) figures[figures.length - 1].shown = { value: duration(h.duration_min), unit: '' };
  // The title arrives in a sentence's lower case ("Yesterday's easy run"), which also reads fine as a heading.
  return (
    <View style={[styles.panel, { backgroundColor: colors.surface }]}>
      <SectionHeader title={h.title} />
      <View style={styles.figures}>
        {figures.map((f) => (
          <View key={f.label} accessible accessibilityLabel={`${f.label}, ${joined(f.shown)}`}>
            <Text variant="bodySmall" color="textSecondary">{f.label}</Text>
            <View style={styles.figure}>
              <Text variant="scoreSuffix">{f.shown.value}</Text>
              {f.shown.unit ? <Text variant="bodySmall" color="textSecondary">{f.shown.unit}</Text> : null}
            </View>
          </View>
        ))}
      </View>
      <Text variant="body" style={styles.line}>{h.line}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { borderRadius: radius.lg, paddingHorizontal: 16, paddingBottom: 16 },
  figures: { flexDirection: 'row', flexWrap: 'wrap', gap: 24 },
  figure: { flexDirection: 'row', alignItems: 'baseline', gap: 4 },
  line: { marginTop: 12 },
});
