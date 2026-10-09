import { ReactNode, useMemo, useState } from 'react';
import { View } from 'react-native';

import { useApi, useLoad } from '../../api/useApi';
import { Trends, TrendValue } from '../../api/client';
import { ReadinessHistory, SleepStages, TrendLine } from '../../components/Charts';
import { Page, PageState } from '../../components/Page';
import { Range, RangeSwitch } from '../../components/RangeSwitch';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { hoursMinutes, monthDay, rangeText } from '../../lib/format';
import { useTheme } from '../../theme/theme';

const value = (r: Trends['rows'][number], key: string) => r[key] as TrendValue;

function average(nums: (number | null)[]): number | null {
  const ok = nums.filter((n): n is number => n !== null);
  return ok.length ? ok.reduce((a, b) => a + b, 0) / ok.length : null;
}

function Section({ title, note, summary, children }: { title: string; note?: string | null; summary?: string | null;
  children: ReactNode }) {
  return (
    <View style={{ marginBottom: 32 }}>
      <SectionHeader title={title} note={note} />
      <View style={{ marginTop: 8 }}>{children}</View>
      {summary ? <Text variant="body" color="textSecondary" style={{ marginTop: 12 }}>{summary}</Text> : null}
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
  const line = (key: string) => rows.map((r) => ({ date: r.night_date, value: value(r, key).value,
    usualLow: value(r, key).usual_low, usualHigh: value(r, key).usual_high }));
  const usual = (key: string) => latest ? rangeText(value(latest, key).usual_low, value(latest, key).usual_high, key) : null;
  const avgScore = average(rows.map((r) => r.readiness.score));
  const avgSleep = average(rows.map((r) => value(r, 'sleep').value));

  const sections = data ? [
    <Section key="readiness" title="Readiness" note={avgScore === null ? null : `Avg ${Math.round(avgScore)}`}
      summary={s.readiness}>
      <ReadinessHistory cutoffs={data.cutoffs} bars={rows.map((r) => ({ date: r.night_date,
        score: r.readiness.score, status: r.readiness.status }))} />
    </Section>,
    <Section key="hrv" title="HRV" note={usual('hrv') && `Usual ${usual('hrv')}`} summary={s.hrv}>
      <TrendLine label="Heart rate variability" points={line('hrv')} />
    </Section>,
    <Section key="rhr" title="Resting heart rate" note={usual('rhr') && `Usual ${usual('rhr')}`} summary={s.rhr}>
      <TrendLine label="Resting heart rate" color={colors.rhr} points={line('rhr')} />
    </Section>,
    <Section key="sleep" title="Sleep" note={avgSleep === null ? null : `Avg ${hoursMinutes(avgSleep)} h`} summary={s.sleep}>
      <SleepStages nights={rows.map((r) => ({ date: r.night_date, deep: r.deep_min, core: r.core_min,
        rem: r.rem_min, other: r.unspecified_min }))} />
    </Section>,
    <Section key="efficiency" title="Sleep efficiency" note={usual('efficiency') && `Usual ${usual('efficiency')}`}
      summary={s.efficiency}>
      <TrendLine label="Sleep efficiency" color={colors.sleep} points={line('efficiency')} />
    </Section>,
  ] : [];

  return (
    <Page>
      <Text variant="labelSmall" color="textSecondary">
        {rows.length ? `${monthDay(rows[0].night_date)} – ${monthDay(latest.night_date)}` : ' '}
      </Text>
      <Text variant="h1" accessibilityRole="header" style={{ marginTop: 4 }}>Trends</Text>
      <View style={{ marginTop: 16, marginBottom: 20, paddingBottom: 0, borderBottomWidth: 1,
        borderBottomColor: colors.border }}>
        <RangeSwitch value={range} onChange={setRange} />
      </View>
      {!data ? <PageState loading={loading} error={error} /> : null}
      {data && rows.length === 0 ? <Text color="textSecondary">No nights yet.</Text> : null}
      {isWide ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', columnGap: 56 }}>
          {sections.map((sec) => <View key={sec.key} style={{ width: '46%', flexGrow: 1 }}>{sec}</View>)}
        </View>
      ) : sections}
      {data ? (
        <Text variant="bodySmall" color="textMuted" style={{ paddingTop: 12, borderTopWidth: 1, borderTopColor: colors.border }}>
          Shaded bands show your usual range, from the 28 nights before each night. Apple Watch data.
          The sentences are placeholders until the explanations are written by the app&apos;s assistant.
        </Text>
      ) : null}
    </Page>
  );
}
