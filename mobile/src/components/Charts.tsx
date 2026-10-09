/**
 * Charts from Figma, drawn from data with SVG:
 *   TrendLine         a nightly line over the shaded band of your usual range
 *   ReadinessHistory  one bar per night, colored by that night's status
 *   SleepStages       one stacked bar per night (deep, core, REM)
 * Missing nights leave a gap instead of being joined or drawn as zero.
 */
import { ReactNode, useState } from 'react';
import { LayoutChangeEvent, View } from 'react-native';
import Svg, { Circle, Line, Path, Rect } from 'react-native-svg';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "2026-09-18" -> "Sep 18" (labels are uppercased by the label style). */
export function shortDate(iso: string): string {
  const [, m, d] = iso.split('-').map(Number);
  return `${MONTHS[m - 1]} ${d}`;
}

function useWidth(): [number, (e: LayoutChangeEvent) => void] {
  const [width, setWidth] = useState(0);
  return [width, (e) => setWidth(Math.round(e.nativeEvent.layout.width))];
}

/** Date labels under a chart: first night on the left, "Last night" on the right. */
function Axis({ first, lastLabel = 'Last night' }: { first?: string; lastLabel?: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 10 }}>
      <Text variant="labelSmall" color="textMuted">{first ? shortDate(first) : ''}</Text>
      <Text variant="labelSmall" color="textMuted">{lastLabel}</Text>
    </View>
  );
}

function Frame({ height, label, children }: { height: number; label: string; children: (w: number) => ReactNode }) {
  const [width, onLayout] = useWidth();
  return (
    <View onLayout={onLayout} accessible accessibilityRole="image" accessibilityLabel={label} style={{ height }}>
      {width > 0 ? children(width) : null}
    </View>
  );
}

// ---------------------------------------------------------------- Trend line

export type TrendPoint = { date: string; value: number | null; usualLow: number | null; usualHigh: number | null };

export function TrendLine({ points, height = 90, label, color }: {
  points: TrendPoint[]; height?: number; label: string; color?: string;
}) {
  const { colors } = useTheme();
  const nums = points.flatMap((p) => [p.value, p.usualLow, p.usualHigh]).filter((v): v is number => v !== null);
  if (points.length === 0 || nums.length === 0) {
    return <Text color="textMuted" style={{ paddingVertical: 24 }}>Not enough nights yet.</Text>;
  }
  let lo = Math.min(...nums);
  let hi = Math.max(...nums);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.15;
  lo -= pad;
  hi += pad;
  const dot = 4;

  return (
    <View>
      <Frame height={height} label={label}>
        {(w) => {
          const x = (i: number) => dot + (points.length === 1 ? (w - 2 * dot) / 2 : (i * (w - 2 * dot)) / (points.length - 1));
          const y = (v: number) => height - ((v - lo) / (hi - lo)) * height;

          // Usual band: a shaded shape following each night's range, broken where there's no baseline.
          const bands: string[] = [];
          let run: number[] = [];
          const flush = () => {
            if (run.length) {
              const top = run.map((i) => `${x(i)},${y(points[i].usualHigh!)}`);
              const bottom = run.slice().reverse().map((i) => `${x(i)},${y(points[i].usualLow!)}`);
              const widen = run.length === 1 ? 3 : 0;   // a single night still shows as a sliver
              bands.push(`M${x(run[0]) - widen},${y(points[run[0]].usualHigh!)} L${top.join(' L')} `
                + `L${x(run[run.length - 1]) + widen},${y(points[run[run.length - 1]].usualLow!)} L${bottom.join(' L')} Z`);
            }
            run = [];
          };
          points.forEach((p, i) => (p.usualLow !== null && p.usualHigh !== null ? run.push(i) : flush()));
          flush();

          // The line, with gaps on missing nights.
          let d = '';
          let pen = false;
          points.forEach((p, i) => {
            if (p.value === null) {
              pen = false;
              return;
            }
            d += `${pen ? 'L' : 'M'}${x(i)},${y(p.value)} `;
            pen = true;
          });
          const lastIndex = points.map((p) => p.value !== null).lastIndexOf(true);

          return (
            <Svg width={w} height={height}>
              {bands.map((b, i) => <Path key={i} d={b} fill={colors.baseline} />)}
              <Path d={d} stroke={color ?? colors.hrv} strokeWidth={1.5} fill="none" strokeLinejoin="round" />
              {lastIndex >= 0 ? (
                <Circle cx={x(lastIndex)} cy={y(points[lastIndex].value!)} r={dot} fill={color ?? colors.hrv} />
              ) : null}
            </Svg>
          );
        }}
      </Frame>
      <Axis first={points[0]?.date} />
    </View>
  );
}

// ---------------------------------------------------------------- Readiness history

export type HistoryBar = { date: string; score: number | null; status: string };

export function ReadinessHistory({ bars, cutoffs, height = 100 }: {
  bars: HistoryBar[]; cutoffs: { low_below: number; ready_from: number }; height?: number;
}) {
  const { colors, statusColor } = useTheme();
  if (bars.length === 0) return <Text color="textMuted" style={{ paddingVertical: 24 }}>No nights yet.</Text>;
  return (
    <View>
      <Frame height={height} label={`Readiness for the last ${bars.length} nights`}>
        {(w) => {
          const gap = bars.length > 40 ? 1 : 4;
          const bw = Math.max(1, (w - gap * (bars.length - 1)) / bars.length);
          const y = (s: number) => height - (s / 100) * height;
          return (
            <Svg width={w} height={height}>
              {[cutoffs.low_below, cutoffs.ready_from].map((c) => (
                <Line key={c} x1={0} x2={w} y1={y(c)} y2={y(c)} stroke={colors.border} strokeWidth={1} />
              ))}
              <Line x1={0} x2={w} y1={height - 0.5} y2={height - 0.5} stroke={colors.borderStrong} strokeWidth={1} />
              {bars.map((b, i) => b.score === null ? null : (
                <Rect key={b.date} x={i * (bw + gap)} y={y(Math.max(b.score, 2))} width={bw}
                  height={height - y(Math.max(b.score, 2))} fill={statusColor(b.status)} />
              ))}
            </Svg>
          );
        }}
      </Frame>
      <Axis first={bars[0]?.date} />
    </View>
  );
}

// ---------------------------------------------------------------- Sleep stages

export type SleepNight = { date: string; deep: number | null; core: number | null; rem: number | null; other: number | null };

export function SleepStages({ nights, height = 110 }: { nights: SleepNight[]; height?: number }) {
  const { colors } = useTheme();
  if (nights.length === 0) return <Text color="textMuted" style={{ paddingVertical: 24 }}>No nights yet.</Text>;
  const total = (n: SleepNight) => (n.deep ?? 0) + (n.core ?? 0) + (n.rem ?? 0) + (n.other ?? 0);
  const top = Math.max(60, ...nights.map(total));
  const hasOther = nights.some((n) => (n.other ?? 0) > 0);
  const legend = [
    { label: 'Deep', color: colors.sleepDeep },
    { label: 'Core', color: colors.sleepCore },
    { label: 'REM', color: colors.sleepRem },
    ...(hasOther ? [{ label: 'Asleep', color: colors.sleep }] : []),
  ];
  return (
    <View>
      <Frame height={height} label={`Sleep stages for the last ${nights.length} nights`}>
        {(w) => {
          const gap = nights.length > 40 ? 1 : 4;
          const bw = Math.max(1, (w - gap * (nights.length - 1)) / nights.length);
          const h = (min: number) => (min / top) * height;
          return (
            <Svg width={w} height={height}>
              {nights.map((n, i) => {
                let base = height;
                // Bottom to top: deep, core, REM, then sleep without a stage (older watches).
                return [[n.deep, colors.sleepDeep], [n.core, colors.sleepCore], [n.rem, colors.sleepRem],
                  [n.other, colors.sleep]].map(([min, fill], k) => {
                  const hh = h((min as number | null) ?? 0);
                  if (hh <= 0) return null;
                  base -= hh;
                  return <Rect key={`${n.date}-${k}`} x={i * (bw + gap)} y={base} width={bw} height={hh} fill={fill as string} />;
                });
              })}
            </Svg>
          );
        }}
      </Frame>
      <Axis first={nights[0]?.date} />
      <View style={{ flexDirection: 'row', gap: 16, marginTop: 10 }}>
        {legend.map((l) => (
          <View key={l.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <View style={{ width: 10, height: 10, backgroundColor: l.color }} />
            <Text variant="labelSmall" color="textSecondary">{l.label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
