import { ReactNode } from 'react';
import { ScrollView, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

/** Scrolling page with the side margins from Figma (20 on iPhone, 48 on a computer). */
export function Page({ children }: { children: ReactNode }) {
  const { colors, isWide } = useTheme();
  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.canvas }}
      contentContainerStyle={{ paddingHorizontal: isWide ? 48 : 20, paddingTop: isWide ? 40 : 16, paddingBottom: 40 }}>
      <View style={{ width: '100%', maxWidth: isWide ? 1112 : undefined, alignSelf: 'center' }}>{children}</View>
    </ScrollView>
  );
}

/** Shown while a page loads or when the server can't be reached. */
export function PageState({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) return <Text color="low" style={{ marginTop: 24 }}>{error}</Text>;
  if (loading) return <Text color="textMuted" style={{ marginTop: 24 }}>Loading…</Text>;
  return null;
}
