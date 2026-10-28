import { useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { Page, PageState } from '../../components/Page';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { useHealthSync } from '../../health/HealthSync';
import { clock, dayLabel, weekdayName, weekdayShort } from '../../lib/format';
import { errorText, useLoad } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';
import { LastNight } from './LastNight';
import { NightlyChart } from './NightlyChart';
import { TimeZoneNote } from './TimeZoneNote';
import { TodaySummary } from './TodaySummary';

export default function TodayScreen() {
  const api = useApi();
  const { colors, isWide } = useTheme();
  const health = useHealthSync();
  // Reload when the tester changes or the phone just sent new Apple Health data.
  const key = useMemo(() => ({ api, v: health.dataVersion }), [api, health.dataVersion]);
  const today = useLoad(() => api.today(), key);
  const trends = useLoad(() => api.trends(14), key);
  const [updating, setUpdating] = useState(false);
  const [updateNote, setUpdateNote] = useState<string | null>(null);

  async function updateNow() {
    setUpdating(true);
    setUpdateNote(null);
    try {
      // Make sure last night's data is on the server first.
      await health.syncNow();
      const r = await api.updateNow();
      if (!r.processed) setUpdateNote(r.message);
      today.reload();
      trends.reload();
    } catch (e) {
      setUpdateNote(errorText(e));
    } finally {
      setUpdating(false);
    }
  }

  const t = today.data;
  if (!t) return <Page><PageState loading={today.loading} error={today.error} /></Page>;

  const top = (
    <View style={[styles.top, { borderBottomColor: colors.borderStrong }]}>
      <Text variant="labelMedium">{dayLabel(t.now_local)}</Text>
      {!isWide && t.updated_at ? <Text variant="labelMedium" color="textSecondary">Synced {clock(t.updated_at)}</Text> : null}
    </View>
  );
  const timeZone = <TimeZoneNote onChanged={() => { today.reload(); trends.reload(); }} />;

  if (!t.readiness) {
    return (
      <Page>
        {top}
        <Text variant="h1" accessibilityRole="header">No nights yet</Text>
        <Text variant="bodyLarge" color="textSecondary" style={styles.noNights}>
          Once your watch has recorded a night of sleep and it has synced, your first night shows here.
          Your score starts after 7 nights.
        </Text>
      </Page>
    );
  }

  const waiting = !!t.night_date && !t.is_last_night;
  const summary = <TodaySummary today={{ ...t, readiness: t.readiness }} waiting={waiting} updating={updating}
    updateNote={updateNote} onUpdateNow={updateNow} />;
  const lastNight = <LastNight today={t} title={waiting ? `${weekdayName(t.night_date!)} night` : 'Last night'} />;

  // The charts end at the night on screen: "Last night", or its short weekday while waiting ("Mon").
  const chartEnd = waiting ? weekdayShort(t.night_date!) : 'Last night';
  const hrvChart = <NightlyChart title="HRV, 14 nights" label="Heart rate variability, last 14 nights" metric="hrv"
    trends={trends} lastLabel={chartEnd} />;
  const rhrChart = <NightlyChart title="Resting heart rate, 14 nights" label="Resting heart rate, last 14 nights"
    metric="rhr" color={colors.rhr} trends={trends} lastLabel={chartEnd} />;

  const checkIn = (
    <View>
      <SectionHeader title="Morning check-in" note="Coming soon" />
      <View style={isWide ? styles.checkInWide : styles.checkIn}>
        <Text variant="body" color="textSecondary" style={isWide ? styles.column : undefined}>
          How do your legs feel? Your answers will teach the score what normal feels like for you.
        </Text>
        <Button title="Start check-in" disabled />
      </View>
    </View>
  );

  const footer = (
    <Text variant="bodySmall" color="textMuted" style={[styles.footer, { borderTopColor: colors.border }]}>
      From your Apple Watch. Score and wording are placeholders while the team decides the formula.
      A guide, not medical advice.
    </Text>
  );

  if (isWide) {
    return (
      <Page>
        {top}
        {timeZone}
        <View style={styles.columns}>
          <View style={styles.column}>{summary}</View>
          <View style={styles.column}>{lastNight}</View>
        </View>
        <View style={[styles.columns, styles.chartsWide]}>
          <View style={styles.column}>{hrvChart}</View>
          <View style={styles.column}>{rhrChart}</View>
        </View>
        <View style={styles.space32}>{checkIn}</View>
        {footer}
      </Page>
    );
  }
  return (
    <Page>
      {top}
      {timeZone}
      {summary}
      <View style={styles.space32}>{lastNight}</View>
      <View style={styles.space8}>{hrvChart}</View>
      <View style={styles.space32}>{checkIn}</View>
      {footer}
    </Page>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: 'row', justifyContent: 'space-between', paddingBottom: 12, marginBottom: 20,
    borderBottomWidth: 1 },
  noNights: { marginTop: 10 },
  checkIn: { gap: 16 },
  checkInWide: { flexDirection: 'row', alignItems: 'center', gap: 24 },
  footer: { marginTop: 24, paddingTop: 12, borderTopWidth: 1 },
  columns: { flexDirection: 'row', gap: 56 },
  column: { flex: 1 },
  chartsWide: { marginTop: 40 },
  space32: { marginTop: 32 },
  space8: { marginTop: 8 },
});
