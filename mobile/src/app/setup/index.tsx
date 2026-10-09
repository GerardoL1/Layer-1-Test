import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { Button } from '../../components/Button';
import { SetupFrame } from '../../components/SetupFrame';
import { TestBuild } from '../../components/TestBuild';
import { Text } from '../../components/Text';
import { useSession } from '../../state/session';
import { useTheme } from '../../theme/theme';

const STEPS = ['Wear your watch to bed.', 'Open the app in the morning.', 'Get a score and a plain reason.'];

/** Setup 1: Welcome. The Test build section picks the server and tester until real accounts exist. */
export default function Welcome() {
  const { colors } = useTheme();
  const { serverUrl, userId } = useSession();
  const [note, setNote] = useState<string | null>(null);

  return (
    <SetupFrame step={0} actions={
      <>
        <Button title="Get started" onPress={() => (serverUrl && userId ? router.push('/setup/health')
          : setNote('First pick a tester or a demo person in Test build below.'))} />
        {note ? <Text variant="bodySmall" color="low">{note}</Text> : null}
        <TestBuild next="/setup/health" />
      </>
    }>
      <Text variant="labelSmall" color="textSecondary">Recovery</Text>
      <Text variant="h1" accessibilityRole="header" style={{ fontSize: 40, lineHeight: 44, marginTop: 72 }}>
        Train when your body is ready.
      </Text>
      <Text variant="bodyLarge" color="textSecondary" style={{ marginTop: 16 }}>
        Recovery reads your Apple Watch overnight and tells you each morning how ready you are to train, and why.
      </Text>
      <View style={{ marginTop: 24, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        {STEPS.map((s, i) => (
          <View key={s} style={{ flexDirection: 'row', alignItems: 'center', gap: 16, minHeight: 54,
            borderTopWidth: 1, borderTopColor: colors.border }}>
            <Text variant="scoreMetric" style={{ fontSize: 24, width: 18 }}>{i + 1}</Text>
            <Text variant="bodyEmphasis">{s}</Text>
          </View>
        ))}
      </View>
    </SetupFrame>
  );
}
