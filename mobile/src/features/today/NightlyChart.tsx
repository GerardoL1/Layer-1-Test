import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, StyleSheet, View } from 'react-native';

import { TrendMetric, Trends } from '../../api/client';
import { TrendLine } from '../../components/Charts';
import { TREND_UNITS } from '../../components/chartText';
import { PageState } from '../../components/Page';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { useTheme } from '../../theme/theme';
import { radius } from '../../theme/tokens';
import { trendPoints } from '../trends/trendData';

type Props = {
  title: string;
  /** Read out by screen readers. */
  label: string;
  metric: TrendMetric;
  trends: { data: Trends | null; loading: boolean; error: string | null };
  /** What the right end of the axis says. */
  lastLabel: string;
};

// shortcut: remembered per app session, so a restart draws the line again. Store it if that bothers anyone.
let drawnOn: string | null = null;

/** A 14-night line on Today in its own panel. The line draws left to right the first time each day. */
export function NightlyChart({ title, label, metric, trends, lastLabel }: Props) {
  const { colors, isWide } = useTheme();
  const today = new Date().toDateString();
  const [reveal] = useState(() => new Animated.Value(drawnOn === today ? 1 : 0));
  const ready = !!trends.data;
  const [chartWidth, setChartWidth] = useState(0);
  useEffect(() => {
    if (!ready || drawnOn === today) return;
    drawnOn = today;
    AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (reduce) reveal.setValue(1);
      else Animated.timing(reveal, { toValue: 1, duration: 600, easing: Easing.out(Easing.cubic),
        useNativeDriver: false }).start();
    });
  }, [ready, today, reveal]);
  const width = reveal.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] });
  // Before 7 scored nights there's no usual range to shade, so the note says when it comes.
  const hasUsual = trends.data?.rows.some((r) => r[metric].usual_low !== null) ?? true;
  const note = hasUsual ? 'Shaded: your usual range' : 'Your usual range appears after 7 scored nights';
  return (
    <View style={[styles.panel, { backgroundColor: colors.surface }]}>
      <SectionHeader title={title} note={isWide ? note : null} />
      {trends.data ? (
        <View style={[styles.card, { backgroundColor: colors.raised }]}
          onLayout={(e) => setChartWidth(e.nativeEvent.layout.width - 24)}>
          {/* The chart keeps its full width and is uncovered from the left, so the line seems to draw itself. */}
          <Animated.View style={[styles.clip, { width }]}>
            <View style={{ width: chartWidth }}>
              <TrendLine label={label} points={trendPoints(trends.data.rows, metric)}
                lastLabel={lastLabel} unit={TREND_UNITS[metric]} />
            </View>
          </Animated.View>
        </View>
      ) : <PageState loading={trends.loading} error={trends.error} />}
      {!isWide ? <Text variant="bodySmall" color="textSecondary" style={styles.caption}>{`${note}.`}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { borderRadius: radius.lg, paddingHorizontal: 16, paddingBottom: 16 },
  card: { borderRadius: radius.md, padding: 12 },
  clip: { overflow: 'hidden' },
  caption: { marginTop: 12 },
});
