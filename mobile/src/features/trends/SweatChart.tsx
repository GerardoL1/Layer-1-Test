import { StyleSheet, View } from 'react-native';

import { Text } from '../../components/Text';
import { monthDay } from '../../lib/format';
import { fluid, joined, Units } from '../../lib/sweat';
import { useTheme } from '../../theme/theme';

type Day = { date: string; fluid_loss_ml: number | null };

/** Sweat lost per day as grey bars, ending yesterday. Days without sweat data get a short stub, not a zero bar. */
export function SweatChart({ days, units, height = 90 }: { days: Day[]; units: Units; height?: number }) {
  const { colors } = useTheme();
  const max = Math.max(...days.map((d) => d.fluid_loss_ml ?? 0));
  const sweaty = days.filter((d) => d.fluid_loss_ml !== null);
  // The bars are a picture, so screen readers get the days with sweat data as a sentence instead.
  const spoken = sweaty.length
    ? `Sweat loss by day: ${sweaty.map((d) => `${monthDay(d.date)} ${joined(fluid(d.fluid_loss_ml!, units))}`).join(', ')}.`
    : 'No sweat data in these days.';
  return (
    <View accessible accessibilityRole="image" accessibilityLabel={spoken}>
      {/* Thinner gaps for long ranges, or 90 bars on a phone have no room left. */}
      <View style={[styles.bars, { height, gap: days.length > 40 ? 1 : 3 }]}>
        {days.map((d) => (
          <View key={d.date} style={[styles.bar, d.fluid_loss_ml === null || max === 0
            ? { height: 2, backgroundColor: colors.border }
            : { height: Math.max(3, (d.fluid_loss_ml / max) * height), backgroundColor: colors.sweat }]} />
        ))}
      </View>
      <View style={styles.axis} aria-hidden>
        <Text variant="labelSmall" color="textSecondary">{days.length ? monthDay(days[0].date) : ''}</Text>
        <Text variant="labelSmall" color="textSecondary">Yesterday</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bars: { flexDirection: 'row', alignItems: 'flex-end' },
  bar: { flex: 1, borderRadius: 2 },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 10 },
});
