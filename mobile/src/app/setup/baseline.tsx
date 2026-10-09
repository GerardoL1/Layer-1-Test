import { router } from 'expo-router';
import { View } from 'react-native';

import { useApi, useLoad } from '../../api/useApi';
import { Button } from '../../components/Button';
import { heroSize } from '../../components/Readiness';
import { SetupFrame } from '../../components/SetupFrame';
import { Text } from '../../components/Text';
import { useTheme } from '../../theme/theme';

/** Setup 4: how many nights the app has, and how close the score is to fully personal. */
export default function BaselineStep() {
  const api = useApi();
  const { colors, isWide, isNarrow } = useTheme();
  const { data: p, loading } = useLoad(() => api.profile().catch(() => null), api);
  const window = p?.baseline_window_nights ?? 28;
  const first = p?.baseline_min_nights ?? 7;
  const have = Math.min(p?.nights_usable ?? 0, window);

  const message = loading ? ' '
    : have === 0 ? `No nights of sleep found yet. Wear your watch to bed, and your first score is ready after ${first} nights.`
    : have < first ? `We found ${have} night${have === 1 ? '' : 's'} of sleep. Your first score is ready after ${first}.`
    : have < window ? `We found ${have} nights of sleep from your watch, so your first score is ready now. `
      + `It gets more personal each night until ${window}.`
    : `We found ${window} or more nights of sleep, so your score is fully personal from today.`;

  return (
    <SetupFrame step={3} actions={<Button title="Go to Today" onPress={() => router.replace('/today')} />}>
      <Text variant="h1" accessibilityRole="header">Learning your normal</Text>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', marginTop: 24 }}>
        <Text variant="scoreHero" style={heroSize(isWide, isNarrow)}>{loading ? '–' : have}</Text>
        <Text variant="scoreSuffix" color="textMuted" style={{ marginLeft: 8, marginBottom: 6 }}>/ {window} nights</Text>
      </View>
      <View accessible accessibilityLabel={`${have} of ${window} nights`} style={{ flexDirection: 'row', gap: 3, marginTop: 20 }}>
        {Array.from({ length: window }, (_, i) => (
          <View key={i} style={{ flex: 1, height: i === first - 1 ? 10 : 7, alignSelf: 'flex-end',
            backgroundColor: i < have ? colors.borderStrong : colors.border }} />
        ))}
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
        <Text variant="labelSmall">First score</Text>
        <Text variant="labelSmall" color="textSecondary">Fully personal</Text>
      </View>
      <Text variant="bodyLarge" color="textSecondary" style={{ marginTop: 16 }}>{message}</Text>
    </SetupFrame>
  );
}
