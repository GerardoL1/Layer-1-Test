/**
 * Train > All workouts: every workout from the last year, newest first, in This week, Last week and
 * one section per month. Figma "All workouts".
 */
import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { Page, PageState } from '../../components/Page';
import { SectionHeader } from '../../components/SectionHeader';
import { SubPageHeader } from '../../components/SubPageHeader';
import { Text } from '../../components/Text';
import { WorkoutRow } from '../../components/WorkoutRow';
import { sections } from '../../lib/sweat';
import { RefreshError } from './RefreshError';
import { tagsFor, useTrainData } from './useTrainData';

export default function AllWorkoutsScreen() {
  const { data, loading, error } = useTrainData();
  const header = (
    <SubPageHeader back="Train" home="/train" label="Workouts" title="All workouts"
      intro="Everything from your Apple Watch and the app, newest first." />
  );
  if (!data) return <Page>{header}<PageState loading={loading} error={error} /></Page>;

  const groups = sections(data.workouts, data.nowLocal);
  return (
    <Page>
      {header}
      <RefreshError error={error} />
      {groups.length === 0 ? (
        <Text variant="body" color="textSecondary">No workouts yet.</Text>
      ) : (
        groups.map((g) => (
          <View key={g.title} style={styles.group}>
            <SectionHeader title={g.title} note={`${g.items.length} ${g.items.length === 1 ? 'workout' : 'workouts'}`} />
            {g.items.map((w) => (
              <WorkoutRow key={w.id} startLocal={w.start_local} type={w.type} minutes={w.duration_min}
                source={w.source} tags={tagsFor(w.id, data.withSweat)}
                onPress={() => router.push({ pathname: '/train/workout/[workoutId]', params: { workoutId: w.id } })} />
            ))}
          </View>
        ))
      )}
    </Page>
  );
}

const styles = StyleSheet.create({
  group: { marginTop: 12, marginBottom: 12 },
});
