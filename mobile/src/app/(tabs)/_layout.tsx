import { Redirect, Slot, usePathname } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Sidebar, TabBar } from '../../components/Navigation';
import { HealthSyncProvider } from '../../health/HealthSync';
import { useSession } from '../../state/session';
import { useTheme } from '../../theme/theme';

/** iPhone: page above a bottom tab bar. Computer (wide): sidebar on the left, page on the right. */
export default function TabsLayout() {
  const { colors, isWide } = useTheme();
  const { serverUrl, userId } = useSession();
  const path = usePathname();
  if (!serverUrl || !userId) return <Redirect href="/setup" />;
  // Screens opened from a tab (like /profile/update-time) cover the tab bar on iPhone, as in Figma.
  const subPage = path.split('/').filter(Boolean).length > 1;

  // Apple Health sync runs while any tab is open (it does nothing on the web).
  if (isWide) {
    return (
      <HealthSyncProvider>
        <View style={[styles.wide, { backgroundColor: colors.canvas }]}>
          <Sidebar footer={`Tester: ${userId}`} />
          <View style={styles.fill}>
            <Slot />
          </View>
        </View>
      </HealthSyncProvider>
    );
  }
  return (
    <HealthSyncProvider>
      <SafeAreaView edges={['top']} style={[styles.fill, { backgroundColor: colors.canvas }]}>
        <View style={styles.fill}>
          <Slot />
        </View>
        {subPage ? null : <TabBar />}
      </SafeAreaView>
    </HealthSyncProvider>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  wide: { flex: 1, flexDirection: 'row' },
});
