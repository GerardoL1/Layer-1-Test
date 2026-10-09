import { useMemo, useState } from 'react';
import { View } from 'react-native';

import { useApi, useLoad } from '../../api/useApi';
import { Today, Trends, TrendValue } from '../../api/client';
import { Button } from '../../components/Button';
import { TrendLine } from '../../components/Charts';
import { useHealthSync } from '../../health/HealthSync';
import { MetricRow } from '../../components/MetricRow';
import { Page, PageState } from '../../components/Page';
import { ReadinessSummary } from '../../components/Readiness';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { clock, dayLabel, metricDisplay } from '../../lib/format';
import { useTheme } from '../../theme/theme';

const LAST_NIGHT_ROWS = ['hrv', 'rhr', 'sleep', 'awakenings'];
const LAST_NIGHT_LABELS: Record<string, string> = { hrv: 'HRV', rhr: 'Resting heart rate', sleep: 'Total sleep',
  awakenings: 'Awakenings' };

function points(trends: Trends | null, key: string) {
  return (trends?.rows ?? []).map((r) => {
    const v = r[key] as TrendValue;
    return { date: r.night_date, value: v.value, usualLow: v.usual_low, usualHigh: v.usual_high };
  });
}

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
      setUpdateNote(e instanceof Error ? e.message : String(e));
    } finally {
      setUpdating(false);
    }
  }

  const t: Today | null = today.data;
  if (!t) return <Page><PageState loading={today.loading} error={today.error} /></Page>;

  const top = (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingBottom: 12, marginBottom: 20,
      borderBottomWidth: 1, borderBottomColor: colors.borderStrong }}>
      <Text variant="labelMedium">{dayLabel(t.now_local)}</Text>
      {!isWide && t.updated_at ? <Text variant="labelMedium" color="textSecondary">Synced {clock(t.updated_at)}</Text> : null}
    </View>
  );

  if (!t.readiness) {
    return (
      <Page>
        {top}
        <Text variant="h1">No nights yet</Text>
        <Text variant="bodyLarge" color="textSecondary" style={{ marginTop: 10 }}>
          Once your watch has recorded a night of sleep and it has synced, your first night shows here.
          Your score starts after 7 nights.
        </Text>
      </Page>
    );
  }

  const summary = (
    <View>
      <ReadinessSummary score={t.readiness.score} status={t.readiness.status} cutoffs={t.cutoffs}
        verdict={t.verdict} reason={t.reason} />
      {t.message || updateNote ? (
        <View style={{ marginTop: 20, padding: 14, backgroundColor: colors.surfaceMuted, gap: 12 }}>
          <Text variant="body" color="textSecondary">{updateNote ?? t.message}</Text>
          {t.can_update_now ? <Button title="Update now" kind="secondary" busy={updating} onPress={updateNow} /> : null}
        </View>
      ) : null}
    </View>
  );

  const rows = LAST_NIGHT_ROWS.map((k) => t.metrics.find((m) => m.key === k)).filter((m) => m !== undefined);
  const lastNight = (
    <View>
      <SectionHeader title={t.is_last_night ? 'Last night' : `Night of ${dayLabel(t.night_date!)}`} note="vs your usual" />
      {rows.map((m) => {
        const d = metricDisplay(m);
        return <MetricRow key={m.key} label={LAST_NIGHT_LABELS[m.key]} shortLabel={m.key === 'rhr' ? 'Resting HR' : undefined}
          value={d.value} unit={d.unit}
          delta={d.delta} direction={m.direction} />;
      })}
      {t.quality_notes ? (
        <Text variant="bodySmall" color="textMuted" style={{ marginTop: 8 }}>Note: {t.quality_notes}.</Text>
      ) : null}
    </View>
  );

  const hrvChart = (
    <View>
      <SectionHeader title="HRV, 14 nights" note="Shaded = your usual" />
      {trends.data ? <TrendLine label="Heart rate variability, last 14 nights" points={points(trends.data, 'hrv')} />
        : <PageState loading={trends.loading} error={trends.error} />}
    </View>
  );
  const rhrChart = (
    <View>
      <SectionHeader title="Resting heart rate, 14 nights" note="Shaded = your usual" />
      {trends.data ? <TrendLine label="Resting heart rate, last 14 nights" color={colors.rhr}
        points={points(trends.data, 'rhr')} /> : <PageState loading={trends.loading} error={trends.error} />}
    </View>
  );

  const checkIn = (
    <View>
      <SectionHeader title="Morning check-in" note="Coming soon" />
      <View style={isWide ? { flexDirection: 'row', alignItems: 'center', gap: 24 } : { gap: 16 }}>
        <Text variant="body" color="textSecondary" style={isWide ? { flex: 1 } : undefined}>
          How do your legs feel? Your answers will teach the score what normal feels like for you.
        </Text>
        <Button title="Start check-in" disabled />
      </View>
    </View>
  );

  const footer = (
    <Text variant="bodySmall" color="textMuted" style={{ marginTop: 24, paddingTop: 12, borderTopWidth: 1,
      borderTopColor: colors.border }}>
      From your Apple Watch. Score and wording are placeholders while the team decides the formula.
      A guide, not medical advice.
    </Text>
  );

  if (isWide) {
    return (
      <Page>
        {top}
        <View style={{ flexDirection: 'row', gap: 56 }}>
          <View style={{ flex: 1 }}>{summary}</View>
          <View style={{ flex: 1 }}>{lastNight}</View>
        </View>
        <View style={{ flexDirection: 'row', gap: 56, marginTop: 40 }}>
          <View style={{ flex: 1 }}>{hrvChart}</View>
          <View style={{ flex: 1 }}>{rhrChart}</View>
        </View>
        <View style={{ marginTop: 32 }}>{checkIn}</View>
        {footer}
      </Page>
    );
  }
  return (
    <Page>
      {top}
      {summary}
      <View style={{ marginTop: 32 }}>{lastNight}</View>
      <View style={{ marginTop: 8 }}>{hrvChart}</View>
      <View style={{ marginTop: 32 }}>{checkIn}</View>
      {footer}
    </Page>
  );
}
