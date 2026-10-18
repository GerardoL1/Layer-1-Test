import { View } from 'react-native';

import { TrendMetric, Trends } from '../../api/client';
import { TrendLine } from '../../components/Charts';
import { TREND_UNITS } from '../../components/chartText';
import { PageState } from '../../components/Page';
import { SectionHeader } from '../../components/SectionHeader';
import { trendPoints } from '../trends/trendData';

type Props = {
  title: string;
  /** Read out by screen readers. */
  label: string;
  metric: TrendMetric;
  color?: string;
  trends: { data: Trends | null; loading: boolean; error: string | null };
  /** What the right end of the axis says. */
  lastLabel: string;
};

/** A 14-night line on Today, with its loading and error states. */
export function NightlyChart({ title, label, metric, color, trends, lastLabel }: Props) {
  return (
    <View>
      <SectionHeader title={title} note="Shaded = your usual" />
      {trends.data ? <TrendLine label={label} color={color} points={trendPoints(trends.data.rows, metric)}
        lastLabel={lastLabel} unit={TREND_UNITS[metric]} />
        : <PageState loading={trends.loading} error={trends.error} />}
    </View>
  );
}
