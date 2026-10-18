import { StyleSheet, View } from 'react-native';

import { Today } from '../../api/client';
import { Button } from '../../components/Button';
import { LiveText } from '../../components/LiveText';
import { ReadinessSummary } from '../../components/Readiness';
import { Text } from '../../components/Text';
import { clock, weekdayName } from '../../lib/format';
import { useTheme } from '../../theme/theme';

type Props = {
  today: Today & { readiness: NonNullable<Today['readiness']> };
  /** True before the update time, while Today still shows an earlier night. */
  waiting: boolean;
  updating: boolean;
  updateNote: string | null;
  onUpdateNow: () => void;
};

/**
 * The score and its reason. Before the update time it also says which night is shown and offers
 * Update now (greyed out until last night's sleep has ended and synced).
 */
export function TodaySummary({ today: t, waiting, updating, updateNote, onUpdateNow }: Props) {
  const { colors } = useTheme();
  return (
    <View>
      <ReadinessSummary score={t.readiness.score} status={t.readiness.status} cutoffs={t.cutoffs}
        verdict={t.verdict} reason={t.reason} />
      {waiting || updateNote ? (
        <View style={[styles.panel, { borderTopColor: colors.border }]}>
          {waiting ? (
            <Text variant="labelMedium" color="textMuted">
              Showing {weekdayName(t.night_date!)} night · Last night updates at {clock(t.update_time)}
            </Text>
          ) : null}
          {waiting ? (
            <Button title="Update now" kind="secondary" busy={updating} disabled={!t.can_update_now}
              onPress={onUpdateNow} style={styles.updateNow} />
          ) : null}
          {updateNote ? <LiveText variant="bodySmall" color="textSecondary">{updateNote}</LiveText> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { marginTop: 24, paddingTop: 14, paddingBottom: 4, gap: 12, borderTopWidth: 1 },
  updateNow: { alignSelf: 'flex-start' },
});
