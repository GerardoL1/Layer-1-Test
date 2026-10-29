/**
 * Readiness scale and Readiness summary from Figma.
 * The 40 / 70 cut-offs come from the server and are placeholders until the team decides.
 */
import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, StyleSheet, View } from 'react-native';

import { ReadinessStatus } from '../api/client';
import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Text } from './Text';

export const STATUS_WORD: Record<ReadinessStatus, string> = {
  low: 'Low',
  moderate: 'Moderate',
  ready: 'Ready',
  building_baseline: 'Learning your normal',
  short_sleep: 'Short night',
  no_data: 'No data',
};

type Cutoffs = { low_below: number; ready_from: number };

/** Where today falls from 0 to 100. The current zone is colored, a tick marks the score. */
export function ReadinessScale({ score, status, cutoffs }: { score: number | null; status: ReadinessStatus; cutoffs: Cutoffs }) {
  const { colors, statusColor } = useTheme();
  const zones = [
    { key: 'low', label: 'Low', from: 0, to: cutoffs.low_below },
    { key: 'moderate', label: 'Moderate', from: cutoffs.low_below, to: cutoffs.ready_from },
    { key: 'ready', label: 'Ready', from: cutoffs.ready_from, to: 100 },
  ];
  return (
    // The score itself is read by the summary above, so the scale only says where the zones are.
    <View accessible role="group"
      accessibilityLabel={`Low below ${cutoffs.low_below}, Moderate ${cutoffs.low_below} to ${cutoffs.ready_from - 1}, `
        + `Ready ${cutoffs.ready_from} and up`}
      style={styles.scale}>
      {zones.map((z) => {
        const on = z.key === status;
        const inZone = score !== null && score >= z.from && (score < z.to || (z.to === 100 && score <= 100));
        return (
          <View key={z.key} style={{ flex: z.to - z.from }}>
            <View style={styles.track}>
              <View style={{ height: on ? 3 : 2, backgroundColor: on ? statusColor(z.key) : colors.border }} />
              {inZone ? (
                <View style={[styles.tick, { left: `${((score! - z.from) / (z.to - z.from)) * 100}%`,
                  backgroundColor: colors.borderStrong }]} />
              ) : null}
            </View>
            <Text variant="labelSmall" style={[styles.zoneLabel, { color: on ? statusColor(z.key) : colors.textMuted }]}>
              {z.label}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

/** Size of the big score: Figma's 168 on a computer, 150 on most phones, 120 on the narrowest. */
export function heroSize(isWide: boolean, isNarrow: boolean) {
  if (isWide) return undefined;
  return isNarrow ? styles.heroNarrow : styles.heroPhone;
}

type SummaryProps = {
  score: number | null;
  status: ReadinessStatus;
  cutoffs: Cutoffs;
  verdict?: string | null;
  reason?: string | null;
};

/** Top of Today: status word, score, scale, one-line verdict and a plain-language reason. */
export function ReadinessSummary({ score, status, cutoffs, verdict, reason }: SummaryProps) {
  const { statusColor, isWide, isNarrow } = useTheme();
  const color = statusColor(status);
  return (
    <View>
      <View style={[styles.statusBar, { backgroundColor: color }]} />
      <Text variant="labelSmall" style={[styles.statusWord, { color }]}>Readiness  ·  {STATUS_WORD[status]}</Text>
      <View accessible role="group" style={styles.score}
        accessibilityLabel={score === null ? 'No score yet' : `Readiness score ${score} out of 100`}>
        <Text variant="scoreHero" aria-hidden style={heroSize(isWide, isNarrow)}>{score ?? '–'}</Text>
        <Text variant="scoreSuffix" color="textMuted" aria-hidden style={styles.outOf}>/ 100</Text>
      </View>
      <View style={styles.scaleSpace}>
        <ReadinessScale score={score} status={status} cutoffs={cutoffs} />
      </View>
      {verdict ? <Text variant="h1" accessibilityRole="header" style={[styles.verdict, { fontSize: isWide ? 30 : 26 }]}>{verdict}</Text> : null}
      {reason ? <Text variant="bodyLarge" color="textSecondary" style={styles.reason}>{reason}</Text> : null}
    </View>
  );
}

/**
 * A person's usual score: the middle half of their recent scores (25th to 75th percentile).
 * Null until there are 7 scored nights, so a new person's band isn't built on a few nights.
 */
export function usualScores(scores: (number | null)[]): [number, number] | null {
  const xs = scores.filter((v): v is number => v !== null).sort((a, b) => a - b);
  if (xs.length < 7) return null;
  const at = (q: number) => Math.round(xs[Math.round(q * (xs.length - 1))]);
  return [at(0.25), at(0.75)];
}

// Spring from the motion spec: no bounce (damping ratio 1), 0.45 s response.
const STIFFNESS = (2 * Math.PI / 0.45) ** 2;
const SPRING = { stiffness: STIFFNESS, damping: 2 * Math.sqrt(STIFFNESS), mass: 1, useNativeDriver: false };

type BandProps = {
  score: number;
  /** The night before's score. The mark glides from there on open. */
  from: number | null;
  /** "Today" or "Monday" while an older night is shown. */
  name: string;
  usual: [number, number] | null;
};

/** Today's readiness band: a track from 0 to 100, your usual range shaded, and a mark at the score. */
export function ReadinessBand({ score, from, name, usual }: BandProps) {
  const { colors } = useTheme();
  const [at] = useState(() => new Animated.Value(from ?? score));
  const [shown, setShown] = useState(from ?? score);
  useEffect(() => {
    const id = at.addListener(({ value }) => setShown(Math.round(value)));
    let anim: Animated.CompositeAnimation | null = null;
    let live = true;
    // Reduced motion: the mark appears in place. Either way the label ends on the exact score.
    AccessibilityInfo.isReduceMotionEnabled().then((reduce) => {
      if (!live) return;
      if (reduce) {
        at.setValue(score);
        setShown(score);
      } else {
        anim = Animated.spring(at, { toValue: score, ...SPRING });
        anim.start(() => live && setShown(score));
      }
    });
    return () => {
      live = false;
      anim?.stop();
      at.removeListener(id);
    };
  }, [at, score]);
  const left = at.interpolate({ inputRange: [0, 100], outputRange: ['0%', '100%'], extrapolate: 'clamp' });
  // Near the right end the label sits left of the mark so it stays on screen.
  const late = score > 70;
  const usualText = usual ? `Your usual: ${usual[0]} to ${usual[1]}` : null;
  return (
    <View accessible role="group"
      accessibilityLabel={`${name}, readiness ${score} out of 100.${usualText ? ` ${usualText}.` : ''}`}>
      <View style={styles.bandLabelRow}>
        <Animated.View style={[late ? { right: at.interpolate({ inputRange: [0, 100],
          outputRange: ['100%', '0%'], extrapolate: 'clamp' }) } : { left }, styles.bandLabel]}>
          <Text variant="labelSmall" style={late ? styles.labelBefore : styles.labelAfter}>{`${name}, ${shown}`}</Text>
        </Animated.View>
      </View>
      <View style={styles.band}>
        <View style={[styles.bandTrack, { backgroundColor: colors.surface }]} />
        {usual ? <View style={[styles.usual, { backgroundColor: colors.baseline, left: `${usual[0]}%`,
          width: `${Math.max(usual[1] - usual[0], 1)}%` }]} /> : null}
        <Animated.View style={[styles.mark, { left, backgroundColor: colors.textPrimary }]} />
      </View>
      <View style={styles.bandEnds} aria-hidden>
        <Text variant="bodySmall" color="textSecondary">Low</Text>
        {usualText ? <Text variant="bodySmall" color="textSecondary">{usualText}</Text> : null}
        <Text variant="bodySmall" color="textSecondary">Ready</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  scale: { flexDirection: 'row', gap: 3 },
  track: { height: 12, justifyContent: 'center' },
  tick: { position: 'absolute', width: 2, height: 12, marginLeft: -1 },
  zoneLabel: { marginTop: 6 },
  heroPhone: { fontSize: 150, lineHeight: 130 },
  heroNarrow: { fontSize: 120, lineHeight: 104 },
  statusBar: { height: 4 },
  statusWord: { marginTop: 20 },
  score: { flexDirection: 'row', alignItems: 'flex-end', marginTop: 8 },
  outOf: { marginLeft: 8, marginBottom: 6 },
  scaleSpace: { marginTop: 16 },
  verdict: { marginTop: 28 },
  reason: { marginTop: 10 },
  bandLabelRow: { height: 20 },
  bandLabel: { position: 'absolute', bottom: 2 },
  labelAfter: { marginLeft: 6 },
  labelBefore: { marginRight: 6 },
  band: { height: 22, justifyContent: 'center' },
  bandTrack: { height: 10, borderRadius: radius.full },
  usual: { position: 'absolute', height: 10, borderRadius: radius.full },
  mark: { position: 'absolute', width: 2, height: 22, marginLeft: -1, borderRadius: 1 },
  bandEnds: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 8, gap: 8 },
});
