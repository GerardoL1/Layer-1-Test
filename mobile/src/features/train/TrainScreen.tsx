/**
 * Train tab: today's suggestion (a placeholder from the readiness status) and the last 7 days of workouts,
 * with a Sweat tag on those that have sweat data. Figma "Train".
 */
import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { ListRow } from '../../components/ListRow';
import { Page, PageState } from '../../components/Page';
import { Panel } from '../../components/Panel';
import { SectionHeader } from '../../components/SectionHeader';
import { Text } from '../../components/Text';
import { WorkoutRow } from '../../components/WorkoutRow';
import { headingLevel } from '../../lib/a11y';
import { dayLabel } from '../../lib/format';
import { lastSevenDays, suggestion } from '../../lib/sweat';
import { useTheme } from '../../theme/theme';
import { RefreshError } from './RefreshError';
import { tagsFor, useTrainData } from './useTrainData';

export default function TrainScreen() {
  const { isWide } = useTheme();
  const { data, loading, error, reload } = useTrainData();
  if (!data) {
    return (
      <Page>
        <Text variant="h1" accessibilityRole="header">Train</Text>
        <PageState loading={loading} error={error} onRetry={reload} />
      </Page>
    );
  }

  const week = lastSevenDays(data.workouts, data.nowLocal);
  const idea = suggestion(data.status);

  const top = (
    <View style={styles.top}>
      <Text variant="bodySmall" color="textSecondary">{dayLabel(data.nowLocal)}</Text>
      <Text variant="h1" accessibilityRole="header" style={styles.title}>Train</Text>
      <RefreshError error={error} />
    </View>
  );

  const suggestionBlock = idea ? (
    <View>
      <Text variant="labelSmall">{`Today's suggestion · readiness ${data.status}`}</Text>
      {/* Looks like a page title, but it's a section under "Train", so it's a level 2 heading. */}
      <Text variant="greeting" accessibilityRole="header" {...headingLevel(2)} style={styles.ideaTitle}>
        {idea.title}
      </Text>
      <Text variant="body" color="textSecondary" style={styles.ideaText}>{idea.text}</Text>
      <Panel style={styles.space16}>
        <ListRow label="Effort" value={idea.effort} />
      </Panel>
      <Text variant="bodySmall" color="textSecondary" style={styles.note}>
        Suggestions follow simple placeholder rules until the team builds the model.
      </Text>
    </View>
  ) : (
    <View>
      <Text variant="labelSmall">{"Today's suggestion"}</Text>
      <Text variant="body" color="textSecondary" style={styles.ideaText}>
        Once your readiness score is ready, a suggestion for today shows here.
      </Text>
    </View>
  );

  const count = `${week.length} ${week.length === 1 ? 'workout' : 'workouts'}`;
  const weekBlock = (
    <View>
      {/* "Last 7 days", not "This week": All workouts uses calendar weeks, and the two shouldn't disagree. */}
      <SectionHeader title="Last 7 days" note={count} />
      <Panel>
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
        <ListRow label="Import a Nix file" value=".xlsx" onPress={() => router.push('/train/import')} />
      </Panel>
      <Text variant="bodySmall" color="textSecondary" style={styles.note}>
        Workouts from your Apple Watch appear here on their own. Open one to add exercises, patch and sweat data.
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
      <View style={styles.space40}>{weekBlock}</View>
    </Page>
  );
}

const styles = StyleSheet.create({
  top: { marginBottom: 28 },
  title: { marginTop: 4 },
  ideaTitle: { marginTop: 8 },
  ideaText: { marginTop: 8 },
  note: { marginTop: 12 },
  empty: { paddingVertical: 14 },
  columns: { flexDirection: 'row', gap: 40 },
  column: { flex: 1 },
  space16: { marginTop: 16 },
  space40: { marginTop: 40 },
});
