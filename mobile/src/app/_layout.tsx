import { Fraunces_600SemiBold } from '@expo-google-fonts/fraunces/600SemiBold';
import { IBMPlexMono_500Medium } from '@expo-google-fonts/ibm-plex-mono/500Medium';
import { IBMPlexSans_400Regular } from '@expo-google-fonts/ibm-plex-sans/400Regular';
import { IBMPlexSans_500Medium } from '@expo-google-fonts/ibm-plex-sans/500Medium';
import { IBMPlexSans_600SemiBold } from '@expo-google-fonts/ibm-plex-sans/600SemiBold';
import { IBMPlexSansCondensed_400Regular } from '@expo-google-fonts/ibm-plex-sans-condensed/400Regular';
import { IBMPlexSansCondensed_600SemiBold } from '@expo-google-fonts/ibm-plex-sans-condensed/600SemiBold';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { SessionProvider, useSession } from '../state/session';
import { ThemeProvider, useTheme } from '../theme/theme';

function Shell() {
  const { colors, isDark } = useTheme();
  const { loaded } = useSession();
  // Wait for the saved session too, so the app doesn't flash Setup before it knows who's signed in.
  if (!loaded) return <View style={{ flex: 1, backgroundColor: colors.canvas }} />;
  return (
    <>
      <StatusBar style={isDark ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.canvas } }} />
    </>
  );
}

export default function RootLayout() {
  const [fontsLoaded] = useFonts({
    Fraunces_600SemiBold,
    IBMPlexSans_400Regular,
    IBMPlexSans_500Medium,
    IBMPlexSans_600SemiBold,
    IBMPlexSansCondensed_400Regular,
    IBMPlexSansCondensed_600SemiBold,
    IBMPlexMono_500Medium,
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
