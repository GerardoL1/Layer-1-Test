import { SafeAreaView } from 'react-native-safe-area-context';

import { Page } from '../../components/Page';
import { TestBuild } from '../../components/TestBuild';
import { Text } from '../../components/Text';
import { useTheme } from '../../theme/theme';

// Temporary Setup for step 4a. Step 4c builds the four designed Setup steps around TestBuild.
export default function SetupScreen() {
  const { colors } = useTheme();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.canvas }}>
      <Page>
        <Text variant="labelSmall" color="textMuted">Recovery</Text>
        <Text variant="h1" style={{ fontSize: 40, lineHeight: 44, marginTop: 48 }}>Train when your body is ready.</Text>
        <TestBuild />
      </Page>
    </SafeAreaView>
  );
}
