import { ReactNode, useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { TrendMetric } from '../../api/client';
import { useApi } from '../../api/useApi';
import { ReadinessHistory, SleepStages, TrendLine } from '../../components/Charts';
import { Page, PageState } from '../../components/Page';
import { Range, RangeSwitch } from '../../components/RangeSwitch';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { hoursMinutes, monthDay, rangeText } from '../../lib/format';
import { useLoad } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';
import { average, trendPoints } from './trendData';

function Section({ title, note, summary, children }: { title: string; note?: string | null; summary?: string | null;
  children: ReactNode }) {
  return (
    <View style={styles.section}>
      <SectionHeader title={title} note={note} />
      <View style={styles.chart}>{children}</View>
      {summary ? <Text variant="body" color="textSecondary" style={styles.summary}>{summary}</Text> : null}
    </View>
  );
}

export default function TrendsScreen() {
  const api = useApi();
  const { colors, isWide } = useTheme();
  const [range, setRange] = useState<Range>(14);
  // Reload when the tester or the range changes.
  const key = useMemo(() => ({ api, range }), [api, range]);
  const { data, error, loading } = useLoad(() => api.trends(range), key);

  const rows = data?.rows ?? [];
  const latest = rows[rows.length - 1];
  const s = data?.summaries ?? {};
  const usual = (m: TrendMetric) => latest ? rangeText(latest[m].usual_low, latest[m].usual_high, m) : null;
  const avgScore = average(rows.map((r) => r.readiness.score));
  const avgSleep = average(rows.map((r) => r.sleep.value));

  const sections = data ? [
    <Section key="readiness" title="Readiness" note={avgScore === null ? null : `Avg ${Math.round(avgScore)}`}
      summary={s.readiness}>
      <ReadinessHistory cutoffs={data.cutoffs} bars={rows.map((r) => ({ date: r.night_date,
        score: r.readiness.score, status: r.readiness.status }))} />
    </Section>,
    <Section key="hrv" title="HRV" note={usual('hrv') && `Usual ${usual('hrv')}`} summary={s.hrv}>
      <TrendLine label="Heart rate variability" points={trendPoints(rows, 'hrv')} unit="ms" />
    </Section>,
    <Section key="rhr" title="Resting heart rate" note={usual('rhr') && `Usual ${usual('rhr')}`} summary={s.rhr}>
      <TrendLine label="Resting heart rate" color={colors.rhr} points={trendPoints(rows, 'rhr')} unit="bpm" />
    </Section>,
    <Section key="sleep" title="Sleep" note={avgSleep === null ? null : `Avg ${hoursMinutes(avgSleep)} h`} summary={s.sleep}>
      <SleepStages nights={rows.map((r) => ({ date: r.night_date, deep: r.deep_min, core: r.core_min,
        rem: r.rem_min, other: r.unspecified_min }))} />
    </Section>,
    <Section key="efficiency" title="Sleep efficiency" note={usual('efficiency') && `Usual ${usual('efficiency')}`}
      summary={s.efficiency}>
      <TrendLine label="Sleep efficiency" color={colors.sleep} points={trendPoints(rows, 'efficiency')} unit="%" />
    </Section>,
  ] : [];

  return (
    <Page>
      <Text variant="labelSmall" color="textSecondary">
        {rows.length ? `${monthDay(rows[0].night_date)} – ${monthDay(latest.night_date)}` : ' '}
      </Text>
      <Text variant="h1" accessibilityRole="header" style={styles.title}>Trends</Text>
      <View style={styles.switch}>
        <RangeSwitch value={range} onChange={setRange} />
      </View>
      {!data ? <PageState loading={loading} error={error} /> : null}
      {data && rows.length === 0 ? <Text color="textSecondary">No nights yet.</Text> : null}
      {isWide ? (
        <View style={styles.grid}>
          {sections.map((sec) => <View key={sec.key} style={styles.cell}>{sec}</View>)}
        </View>
      ) : sections}
      {data ? (
        <Text variant="bodySmall" color="textMuted" style={styles.footer}>
          Shaded bands show your usual range, from the 28 nights before each night. Apple Watch data.
          The sentences are placeholders until the explanations are written by the app&apos;s assistant.
        </Text>
      ) : null}
    </Page>
  );
}

const styles = StyleSheet.create({
  section: { marginBottom: 32 },
  chart: { marginTop: 8 },
  summary: { marginTop: 12 },
  title: { marginTop: 4 },
  switch: { marginTop: 16, marginBottom: 28 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 56 },
  cell: { width: '46%', flexGrow: 1 },
  footer: { marginTop: 8 },
});
