import { InstrumentSans_400Regular } from '@expo-google-fonts/instrument-sans/400Regular';
import { InstrumentSans_500Medium } from '@expo-google-fonts/instrument-sans/500Medium';
import { InstrumentSans_600SemiBold } from '@expo-google-fonts/instrument-sans/600SemiBold';
import { InstrumentSerif_400Regular } from '@expo-google-fonts/instrument-serif/400Regular';
import { useFonts } from 'expo-font';
import { Stack, usePathname } from 'expo-router';
import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { Platform, StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { pageTitle } from '../lib/a11y';
import { SessionProvider, useSession } from '../state/session';
import { ThemeProvider, useTheme } from '../theme/theme';

function Shell() {
  const { colors, isDark } = useTheme();
  const { loaded } = useSession();
  const path = usePathname();
  useEffect(() => {
    if (Platform.OS === 'web') document.title = pageTitle(path);
  }, [path]);
  // Wait for the saved session too, so the app doesn't flash Setup before it knows who's signed in.
  if (!loaded) return <View style={[styles.fill, { backgroundColor: colors.canvas }]} />;
  return (
    <>
      <StatusBar style={isDark ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.canvas } }} />
    </>
  );
}

export default function RootLayout() {
  const [fontsLoaded] = useFonts({
    InstrumentSans_400Regular,
    InstrumentSans_500Medium,
    InstrumentSans_600SemiBold,
    InstrumentSerif_400Regular,
  });
  if (!fontsLoaded) return null;
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <ThemeProvider>
          <Shell />
        </ThemeProvider>
      </SessionProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
});
