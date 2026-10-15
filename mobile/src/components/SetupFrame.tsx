import { Redirect } from 'expo-router';
import { ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useSession } from '../state/session';
import { useTheme } from '../theme/theme';
import { Text } from './Text';

/**
 * Layout shared by the Setup steps: progress bars, content, and the buttons pinned
 * to the bottom on iPhone. On a computer it's a centered 560-wide column.
 * step 0 = Welcome, which has no progress bar. Steps 1 to 3 need a tester picked first.
 */
export function SetupFrame({ step, children, actions }: { step: 0 | 1 | 2 | 3; children: ReactNode; actions: ReactNode }) {
  const { colors, isWide } = useTheme();
  const { serverUrl, userId } = useSession();
  if (step > 0 && (!serverUrl || !userId)) return <Redirect href="/setup" />;

  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: colors.canvas }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingTop: isWide ? 120 : 24 }]}>
        <View style={styles.column}>
          {step > 0 ? (
            <View accessible accessibilityLabel={`Step ${step} of 3`} style={styles.progress}>
              <Text variant="labelSmall" color="textSecondary">Step {step} of 3</Text>
              <View style={styles.bars}>
                {[1, 2, 3].map((i) => (
                  <View key={i} style={[styles.bar, { backgroundColor: i <= step ? colors.borderStrong : colors.border }]} />
                ))}
              </View>
            </View>
          ) : null}
          <View style={styles.grow}>{children}</View>
          <View style={styles.actions}>{actions}</View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  content: { flexGrow: 1, paddingHorizontal: 20, paddingBottom: 24 },
  column: { flexGrow: 1, width: '100%', maxWidth: 560, alignSelf: 'center' },
  progress: { marginBottom: 24 },
  bars: { flexDirection: 'row', gap: 4, marginTop: 8 },
  bar: { flex: 1, height: 3 },
  grow: { flexGrow: 1 },
  actions: { marginTop: 32, gap: 12 },
});
