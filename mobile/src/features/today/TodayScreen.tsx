import { useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { Notice } from '../../components/Notice';
import { Page, PageState } from '../../components/Page';
import { usualScores } from '../../components/Readiness';
import { Text } from '../../components/Text';
import { useHealthSync } from '../../health/HealthSync';
import { clock, dayLabel, fullDay, partOfDay, weekdayShort } from '../../lib/format';
import { errorText, useLoad } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';
import { LastNight } from './LastNight';
import { NightlyChart } from './NightlyChart';
import { TimeZoneNote } from './TimeZoneNote';
import { TodaySummary } from './TodaySummary';
import { WhatMoved } from './WhatMoved';
import { YesterdaysRun } from './YesterdaysRun';

/** The device's own clock, for the greeting when Today itself couldn't load. */
function nowLocal(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function TodayScreen() {
  const api = useApi();
  const { isWide } = useTheme();
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
  if (!t) {
    if (!today.error) return <Page><PageState loading={today.loading} error={null} /></Page>;
    return (
      <Page>
        <Text variant={isWide ? 'greetingLarge' : 'greeting'} accessibilityRole="header">{`${partOfDay(nowLocal())}.\nWe can’t load today.`}</Text>
        <Text variant="bodyLarge" color="textSecondary" style={styles.lead}>{today.error}</Text>
        <Button title="Try again" onPress={today.reload} style={styles.retry} />
      </Page>
    );
  }

  // Phone sync trouble doesn't stop Today, it says what's shown and offers to try again.
  const syncFailed = health.lastError ? (
    <View style={styles.syncFailed}>
      <Notice type="warning" label="Couldn’t sync" live
        action={{ label: health.syncing ? 'Syncing…' : 'Try again', onPress: health.syncNow }}>
        {`Showing data from ${t.updated_at ? `${dayLabel(t.updated_at)}, ${clock(t.updated_at)}` : 'earlier'}. `
          + health.lastError}
      </Notice>
    </View>
  ) : null;

  if (!t.readiness) {
    return (
      <Page>
        {syncFailed}
        <Text variant="bodySmall" color="textSecondary">{fullDay(t.now_local)}</Text>
        <Text variant={isWide ? 'greetingLarge' : 'greeting'} accessibilityRole="header" style={styles.greeting}>
          {`${partOfDay(t.now_local)}.\nNo nights yet.`}
        </Text>
        <Text variant="bodyLarge" color="textSecondary" style={styles.lead}>
          Once your watch has recorded a night of sleep and it has synced, your first night shows here.
          Your score starts after 7 nights.
        </Text>
      </Page>
    );
  }

  const waiting = !!t.night_date && !t.is_last_night;
  const rows = trends.data?.rows ?? [];
  const shown = rows.findIndex((r) => r.night_date === t.night_date);
  const previous = shown > 0 ? rows[shown - 1].readiness.score : null;
  const night = t.metrics.find((m) => m.key === 'hrv');
  // The charts end at the night on screen: "Last night", or its short weekday while waiting ("Mon").
  const chartEnd = `${waiting ? weekdayShort(t.night_date!) : 'Last night'}`
    + (night?.value != null ? `, ${Math.round(night.value)} ms` : ': not recorded');
  const chart = (
    <NightlyChart title="HRV, last 14 nights" label="Heart rate variability, last 14 nights" metric="hrv"
      trends={trends} lastLabel={chartEnd} />
  );

  return (
    <Page>
      {syncFailed}
      {t.readiness.illness_flag ? (
        <View style={styles.syncFailed}>
          <Notice type="warning" label="Possible illness">
            Rest today, drink fluids, and check in with a doctor if you feel unwell.
          </Notice>
        </View>
      ) : null}
      <TodaySummary today={{ ...t, readiness: t.readiness }} waiting={waiting} previous={previous}
        usual={usualScores(rows.map((r) => r.readiness.score))} updating={updating} updateNote={updateNote}
        onUpdateNow={updateNow} notice={<TimeZoneNote onChanged={() => { today.reload(); trends.reload(); }} />} />
      <View style={styles.space32}><LastNight today={t} /></View>
      {/* Figma: on a computer the chart and What moved your score sit side by side. */}
      {isWide ? (
        <View style={[styles.space12, styles.columns]}>
          <View style={styles.wideChart}>{chart}</View>
          <View style={styles.column}><WhatMoved today={t} /></View>
        </View>
      ) : (
        <>
          <View style={styles.space12}>{chart}</View>
          <View style={styles.space12}><WhatMoved today={t} /></View>
        </>
      )}
      <View style={styles.space12}><YesterdaysRun today={t} /></View>
      <Text variant="bodySmall" color="textMuted" style={[styles.footer, isWide && styles.footerWide]}>
        From your Apple Watch. Score and wording are placeholders while the team builds the model.
        A guide, not medical advice.
      </Text>
    </Page>
  );
}

const styles = StyleSheet.create({
  greeting: { marginTop: 8 },
  lead: { marginTop: 12 },
  retry: { alignSelf: 'flex-start', marginTop: 16 },
  syncFailed: { marginBottom: 24 },
  space32: { marginTop: 32 },
  space12: { marginTop: 12 },
  columns: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  wideChart: { flex: 2 },
  column: { flex: 1 },
  footer: { marginTop: 24 },
  footerWide: { maxWidth: 640 },
});
