import { Redirect, Slot } from 'expo-router';
import { View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Sidebar, TabBar } from '../../components/Navigation';
import { HealthSyncProvider } from '../../health/HealthSync';
import { useSession } from '../../state/session';
import { useTheme } from '../../theme/theme';

/** iPhone: page above a bottom tab bar. Computer (wide): sidebar on the left, page on the right. */
export default function TabsLayout() {
  const { colors, isWide } = useTheme();
  const { serverUrl, userId } = useSession();
  if (!serverUrl || !userId) return <Redirect href="/setup" />;

  // Apple Health sync runs while any tab is open (it does nothing on the web).
  if (isWide) {
    return (
      <HealthSyncProvider>
        <View style={{ flex: 1, flexDirection: 'row', backgroundColor: colors.canvas }}>
          <Sidebar footer={`Tester: ${userId}`} />
          <View style={{ flex: 1 }}>
            <Slot />
          </View>
        </View>
      </HealthSyncProvider>
    );
  }
  return (
    <HealthSyncProvider>
      <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.canvas }}>
        <View style={{ flex: 1 }}>
          <Slot />
        </View>
        <TabBar />
      </SafeAreaView>
    </HealthSyncProvider>
  );
}
