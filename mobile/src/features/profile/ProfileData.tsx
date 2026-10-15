import { router } from 'expo-router';
import { Platform, StyleSheet, View } from 'react-native';

import { Profile } from '../../api/client';
import { ListRow } from '../../components/ListRow';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { useHealthSync } from '../../health/HealthSync';
import { clock, dayLabel, rangeText } from '../../lib/format';

const USUAL_LABELS: Record<string, string> = { hrv: 'HRV', rhr: 'Resting heart rate', sleep: 'Total sleep',
  fragmentation: 'Awakenings' };

/** Left side of Profile: where the data comes from, and the person's usual ranges. */
export function ProfileData({ profile: p, reload }: { profile: Profile; reload: () => void }) {
  const health = useHealthSync();
  const watch = p.sources.some((x) => x.includes('Apple Watch'));
  return (
    <View>
      <SectionHeader title="Data source" note="Apple Watch only" />
      {Platform.OS === 'ios'
        ? (
          <View>
            <ListRow label="Apple Health" value={health.syncing ? 'Syncing…' : 'Sync now'} onPress={async () => {
              await health.syncNow();
              reload();
            }} />
            {health.lastError || health.lastResult ? (
              <Text variant="bodySmall" color={health.lastError ? 'low' : 'textSecondary'} style={styles.syncNote}>
                {health.lastError ?? health.lastResult?.message}
              </Text>
            ) : null}
            <ListRow label="Permissions" value="Set up" onPress={() => router.push('/setup/health')} />
          </View>
        )
        : <ListRow label="Apple Health" value="iPhone app or export" />}
      <ListRow label="Watch" value={watch ? 'Apple Watch' : 'Not found yet'} />
      <ListRow label="Last update" value={p.last_update_local
        ? `${dayLabel(p.last_update_local)}, ${clock(p.last_update_local)}` : 'Not yet'} />
      <ListRow label="What we read" value="HRV, heart rate, sleep" />

      <View style={styles.usual}>
        <SectionHeader title="Your usual" note={`Previous ${p.baseline_window_nights} nights`} />
        {p.usual_ranges.filter((u) => USUAL_LABELS[u.key]).map((u) => (
          <ListRow key={u.key} label={USUAL_LABELS[u.key]}
            value={rangeText(u.usual_low, u.usual_high, u.key) ?? `Needs ${p.baseline_min_nights} nights`} />
        ))}
        {p.usual_ranges.length === 0 ? <ListRow label="Usual ranges" value={`Need ${p.baseline_min_nights} nights`} /> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  syncNote: { paddingBottom: 12 },
  usual: { marginTop: 32 },
});
