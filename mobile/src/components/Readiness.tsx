/**
 * Readiness scale and Readiness summary from Figma.
 * The 40 / 70 cut-offs come from the server and are placeholders until the team decides.
 */
import { View } from 'react-native';

import { ReadinessStatus } from '../api/client';
import { useTheme } from '../theme/theme';
import { Text } from './Text';

const STATUS_WORD: Record<ReadinessStatus, string> = {
  low: 'Low',
  moderate: 'Moderate',
  ready: 'Ready',
  building_baseline: 'Learning your normal',
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
    <View accessible accessibilityLabel={score === null ? 'No score yet' : `Score ${score} of 100, ${STATUS_WORD[status]}`}
      style={{ flexDirection: 'row', gap: 3 }}>
      {zones.map((z) => {
        const on = z.key === status;
        const inZone = score !== null && score >= z.from && (score < z.to || (z.to === 100 && score <= 100));
        return (
          <View key={z.key} style={{ flex: z.to - z.from }}>
            <View style={{ height: 12, justifyContent: 'center' }}>
              <View style={{ height: on ? 3 : 2, backgroundColor: on ? statusColor(z.key) : colors.border }} />
              {inZone ? (
                <View style={{ position: 'absolute', left: `${((score! - z.from) / (z.to - z.from)) * 100}%`,
                  width: 2, height: 12, marginLeft: -1, backgroundColor: colors.borderStrong }} />
              ) : null}
            </View>
            <Text variant="labelSmall" style={{ marginTop: 6, color: on ? statusColor(z.key) : colors.textMuted }}>
              {z.label}
            </Text>
          </View>
        );
      })}
    </View>
  );
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
  const { statusColor, isWide } = useTheme();
  const color = statusColor(status);
  return (
    <View>
      <View style={{ height: 4, backgroundColor: color }} />
      <Text variant="labelSmall" style={{ color, marginTop: 20 }}>Readiness  ·  {STATUS_WORD[status]}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', marginTop: 8 }}>
        <Text variant="scoreHero" accessibilityLabel={score === null ? 'No score yet' : `${score} out of 100`}
          style={isWide ? undefined : { fontSize: 150, lineHeight: 130 }}>
          {score ?? '–'}
        </Text>
        <Text variant="scoreSuffix" color="textMuted" style={{ marginLeft: 8, marginBottom: 6 }}>/ 100</Text>
      </View>
      <View style={{ marginTop: 16 }}>
        <ReadinessScale score={score} status={status} cutoffs={cutoffs} />
      </View>
      {verdict ? <Text variant="h1" style={{ marginTop: 28, fontSize: isWide ? 30 : 26 }}>{verdict}</Text> : null}
      {reason ? <Text variant="bodyLarge" color="textSecondary" style={{ marginTop: 10 }}>{reason}</Text> : null}
    </View>
  );
}
