/**
 * Component gallery, for checking the components against Figma (open /components).
 * Uses made-up sample data. Not linked from the app.
 */
import { useState } from 'react';
import { View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '../components/Button';
import { ReadinessHistory, SleepStages, TrendLine } from '../components/Charts';
import { ListRow } from '../components/ListRow';
import { MetricRow } from '../components/MetricRow';
import { Page } from '../components/Page';
import { Range, RangeSwitch } from '../components/RangeSwitch';
import { ReadinessScale, ReadinessSummary } from '../components/Readiness';
import { SectionHeader } from '../components/SectionHeader';
import { Text } from '../components/Text';
import { useSession } from '../state/session';
import { useTheme } from '../theme/theme';

const CUT = { low_below: 40, ready_from: 70 };
const dates = Array.from({ length: 14 }, (_, i) => `2026-09-${String(17 + i).padStart(2, '0')}`);
const hrv = [55, 57, 53, 56, 55, 57, 54, 53, 56, 47, 42, 39, 36, 33];
const rhr = [55, 54, 56, 55, 56, 54, 55, 56, 55, 58, 60, 61, 62, 63];
const scores = [72, 76, 64, 78, 74, 69, 77, 71, 60, 52, 47, 38, 33, 28];
const status = (s: number) => (s < 40 ? 'low' : s < 70 ? 'moderate' : 'ready');

export default function Gallery() {
  const { colors } = useTheme();
  const { appearance, update } = useSession();
  const [range, setRange] = useState<Range>(14);
  const gap = { marginTop: 40 };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.canvas }}>
      <Page>
        <Text variant="h1">Components</Text>
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
          {(['light', 'dark', 'system'] as const).map((a) => (
            <Button key={a} title={a} kind={appearance === a ? 'primary' : 'secondary'} onPress={() => update({ appearance: a })} />
          ))}
        </View>

        <View style={gap}><SectionHeader title="Readiness summary" note="Low · Moderate · Ready" /></View>
        {[28, 55, 82].map((s) => (
          <View key={s} style={{ marginTop: 24, maxWidth: 393 }}>
            <ReadinessSummary score={s} status={status(s)} cutoffs={CUT} verdict="Take a recovery day."
              reason="Your HRV is well below normal for you and your resting heart rate stayed higher overnight." />
          </View>
        ))}
        <View style={{ marginTop: 24, maxWidth: 393 }}>
          <ReadinessSummary score={null} status="building_baseline" cutoffs={CUT} />
        </View>

        <View style={gap}><SectionHeader title="Readiness scale" /></View>
        {[28, 55, 82].map((s) => (
          <View key={s} style={{ marginTop: 16, maxWidth: 353 }}><ReadinessScale score={s} status={status(s)} cutoffs={CUT} /></View>
        ))}

        <View style={gap}><SectionHeader title="Last night" note="vs your usual" /></View>
        <MetricRow label="HRV" value="33" unit="ms" delta="-18%" direction="worse" />
        <MetricRow label="Resting heart rate" value="57" unit="bpm" delta="Usual" direction="usual" />
        <MetricRow label="Total sleep" value="7:52" unit="h" delta="+31 min" direction="better" />
        <MetricRow label="Awakenings" value="–" direction={null} />

        <View style={gap}><SectionHeader title="HRV, 14 nights" note="Shaded = your usual" /></View>
        <TrendLine label="HRV trend" points={dates.map((d, i) => ({ date: d, value: i === 5 ? null : hrv[i],
          usualLow: i < 2 ? null : 49, usualHigh: i < 2 ? null : 58 }))} />
        <View style={gap}><SectionHeader title="Resting heart rate" note="Usual 55-59 bpm" /></View>
        <TrendLine label="Resting HR trend" color={colors.rhr} points={dates.map((d, i) => ({ date: d, value: rhr[i],
          usualLow: 54, usualHigh: 57 }))} />

        <View style={gap}><SectionHeader title="Readiness" note="Avg 60" /></View>
        <ReadinessHistory cutoffs={CUT} bars={dates.map((d, i) => ({ date: d, score: i === 3 ? null : scores[i],
          status: status(scores[i]) }))} />

        <View style={gap}><SectionHeader title="Sleep" note="Avg 7:01 h" /></View>
        <SleepStages nights={dates.map((d, i) => ({ date: d, deep: 60 - i, core: 260 - i * 4, rem: 95,
          other: i === 7 ? 40 : 0 }))} />

        <View style={gap}><SectionHeader title="Range switch" /></View>
        <View style={{ marginTop: 8 }}><RangeSwitch value={range} onChange={setRange} /></View>

        <View style={gap}><SectionHeader title="Settings" /></View>
        <ListRow label="Apple Health" value="Connected" valueColor="ready" />
        <ListRow label="Appearance" value="Match system" onPress={() => {}} />
        <ListRow label="Check-in reminder" comingSoon onPress={() => {}} />
        <ListRow label="Delete my data" danger comingSoon />

        <View style={gap}><SectionHeader title="Buttons" /></View>
        <View style={{ gap: 12, maxWidth: 353 }}>
          <Button title="Start check-in" />
          <Button title="Update now" kind="secondary" />
          <Button title="Working" busy />
        </View>
      </Page>
    </SafeAreaView>
  );
}
