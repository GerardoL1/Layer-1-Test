import { Redirect, Slot } from 'expo-router';
import { View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Sidebar, TabBar } from '../../components/Navigation';
import { useSession } from '../../state/session';
import { useTheme } from '../../theme/theme';

/** iPhone: page above a bottom tab bar. Computer (wide): sidebar on the left, page on the right. */
export default function TabsLayout() {
  const { colors, isWide } = useTheme();
  const { serverUrl, userId } = useSession();
  if (!serverUrl || !userId) return <Redirect href="/setup" />;

  if (isWide) {
    return (
      <View style={{ flex: 1, flexDirection: 'row', backgroundColor: colors.canvas }}>
        <Sidebar footer={`Tester: ${userId}`} />
        <View style={{ flex: 1 }}>
          <Slot />
        </View>
      </View>
    );
  }
  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.canvas }}>
      <View style={{ flex: 1 }}>
        <Slot />
      </View>
      <TabBar />
    </SafeAreaView>
  );
}
