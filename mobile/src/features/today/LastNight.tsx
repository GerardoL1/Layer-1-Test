import { StyleSheet, View } from 'react-native';

import { Today } from '../../api/client';
import { MetricRow } from '../../components/MetricRow';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { metricDisplay } from '../../lib/format';

const ROWS = ['hrv', 'rhr', 'sleep', 'awakenings'];
const LABELS: Record<string, string> = { hrv: 'HRV', rhr: 'Resting heart rate', sleep: 'Total sleep',
  awakenings: 'Awakenings' };

/** The "Last night vs your usual" table. title is "Last night", or "Mon night" while waiting. */
export function LastNight({ today: t, title }: { today: Today; title: string }) {
  const rows = ROWS.map((k) => t.metrics.find((m) => m.key === k)).filter((m) => m !== undefined);
  return (
    <View>
      <SectionHeader title={title} note="vs your usual" />
      {rows.map((m) => {
        const d = metricDisplay(m);
        return <MetricRow key={m.key} label={LABELS[m.key]} shortLabel={m.key === 'rhr' ? 'Resting HR' : undefined}
          value={d.value} unit={d.unit} delta={d.delta} direction={m.direction} />;
      })}
      {t.quality_notes ? <Text variant="bodySmall" color="textMuted" style={styles.note}>Note: {t.quality_notes}.</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  note: { marginTop: 8 },
});
