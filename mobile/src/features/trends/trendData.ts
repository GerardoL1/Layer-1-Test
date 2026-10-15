/** Turning Trends rows into what the charts and notes need. */
import { TrendMetric, TrendRow } from '../../api/client';
import { TrendPoint } from '../../components/Charts';

export function trendPoints(rows: TrendRow[], metric: TrendMetric): TrendPoint[] {
  return rows.map((r) => ({ date: r.night_date, value: r[metric].value, usualLow: r[metric].usual_low,
    usualHigh: r[metric].usual_high }));
}

export function average(nums: (number | null)[]): number | null {
  const ok = nums.filter((n): n is number => n !== null);
  return ok.length ? ok.reduce((a, b) => a + b, 0) / ok.length : null;
}
