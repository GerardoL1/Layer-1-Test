/**
 * Train tab: today's suggestion (a placeholder from the readiness status) and this week's workouts,
 * with a SWEAT tag on those that have sweat data. Figma "Train".
 */
import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { ListRow } from '../../components/ListRow';
import { Page, PageState } from '../../components/Page';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { WorkoutRow } from '../../components/WorkoutRow';
import { headingLevel } from '../../lib/a11y';
import { dayLabel } from '../../lib/format';
import { lastSevenDays, suggestion } from '../../lib/sweat';
import { useTheme } from '../../theme/theme';
import { RefreshError } from './RefreshError';
import { tagsFor, useTrainData } from './useTrainData';

const STATUS_WORD: Record<string, string> = { low: 'Low', moderate: 'Moderate', ready: 'Ready' };

export default function TrainScreen() {
  const { colors, isWide } = useTheme();
  const { data, loading, error } = useTrainData();
  if (!data) return <Page><PageState loading={loading} error={error} /></Page>;

  const week = lastSevenDays(data.workouts, data.nowLocal);
  const idea = suggestion(data.status);
  const tone = data.status === 'low' || data.status === 'moderate' || data.status === 'ready' ? data.status : null;

  const top = (
    <View style={styles.top}>
      <Text variant="labelMedium">{dayLabel(data.nowLocal)}</Text>
      <Text variant="h1" accessibilityRole="header" style={styles.title}>Train</Text>
      <RefreshError error={error} />
    </View>
  );

  const suggestionBlock = (
    <View style={[styles.suggestion, { borderTopColor: tone ? colors[tone] : colors.borderStrong }]}>
      {idea && tone ? (
        <>
          <Text variant="labelSmall" color={tone}>
            {`Today's suggestion · Readiness ${STATUS_WORD[tone]}`}
          </Text>
          {/* Looks like a page title, but it's a section under "Train", so it's a level 2 heading. */}
          <Text variant="h1" accessibilityRole="header" {...headingLevel(2)} style={styles.ideaTitle}>
            {idea.title}
          </Text>
          <Text variant="bodyLarge" color="textSecondary" style={styles.ideaText}>{idea.text}</Text>
          <View style={styles.rows}>
            <ListRow label="Effort" value={idea.effort} />
          </View>
          <Text variant="bodySmall" color="textMuted" style={styles.note}>
            Suggestions follow simple placeholder rules until the team builds the model.
          </Text>
        </>
      ) : (
        <>
          <Text variant="labelSmall" color="textSecondary">{"Today's suggestion"}</Text>
          <Text variant="body" color="textSecondary" style={styles.ideaText}>
            Once your readiness score is ready, a suggestion for today shows here.
          </Text>
        </>
      )}
    </View>
  );

  const count = `${week.length} ${week.length === 1 ? 'workout' : 'workouts'}`;
  const weekBlock = (
    <View>
      {/* "Last 7 days", not "This week": All workouts uses calendar weeks, and the two shouldn't disagree. */}
      <SectionHeader title="Last 7 days" note={count} />
      {week.length === 0 ? (
        <Text variant="body" color="textSecondary" style={styles.empty}>No workouts in the last 7 days.</Text>
      ) : (
        week.map((w) => (
          <WorkoutRow key={w.id} startLocal={w.start_local} type={w.type} minutes={w.duration_min} source={w.source}
            tags={tagsFor(w.id, data.withSweat)}
            onPress={() => router.push({ pathname: '/train/workout/[workoutId]', params: { workoutId: w.id } })} />
        ))
      )}
      <ListRow label="All workouts" onPress={() => router.push('/train/workouts')} />
      {/* Not in Figma: a way in for a Nix workout the app doesn't have yet. The file finds its workout. */}
      <ListRow label="Import a Nix file" value=".xlsx" onPress={() => router.push('/train/import')} />
      <Text variant="bodySmall" color="textMuted" style={[styles.note, { borderTopColor: colors.border }]}>
        Open a workout to see its sweat data.
      </Text>
    </View>
  );

  if (isWide) {
    return (
      <Page>
        {top}
        <View style={styles.columns}>
          <View style={styles.column}>{suggestionBlock}</View>
          <View style={styles.column}>{weekBlock}</View>
        </View>
      </Page>
    );
  }
  return (
    <Page>
      {top}
      {suggestionBlock}
      <View style={styles.space32}>{weekBlock}</View>
    </Page>
  );
}

const styles = StyleSheet.create({
  top: { marginBottom: 16 },
  title: { marginTop: 4 },
  suggestion: { borderTopWidth: 3, paddingTop: 14 },
  ideaTitle: { marginTop: 8 },
  ideaText: { marginTop: 8 },
  rows: { marginTop: 12, borderBottomWidth: 0 },
  note: { marginTop: 10 },
  empty: { paddingVertical: 12 },
  columns: { flexDirection: 'row', gap: 56 },
  column: { flex: 1 },
  space32: { marginTop: 32 },
});
