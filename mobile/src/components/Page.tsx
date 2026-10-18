import { ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { LiveText } from './LiveText';

/** Scrolling page with the side margins from Figma (20 on iPhone, 48 on a computer). */
export function Page({ children }: { children: ReactNode }) {
  const { colors, isWide } = useTheme();
  return (
    <ScrollView role="main" style={[styles.page, { backgroundColor: colors.canvas }]}
      contentContainerStyle={isWide ? styles.contentWide : styles.content}>
      <View style={[styles.column, isWide && styles.columnWide]}>{children}</View>
    </ScrollView>
  );
}

/** Shown while a page loads or when the server can't be reached. */
export function PageState({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) return <LiveText error color="low" style={styles.state}>{error}</LiveText>;
  if (loading) return <LiveText color="textMuted" style={styles.state}>Loading…</LiveText>;
  return null;
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  content: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 40 },
  contentWide: { paddingHorizontal: 48, paddingTop: 40, paddingBottom: 40 },
  column: { width: '100%', alignSelf: 'center' },
  columnWide: { maxWidth: 1112 },
  state: { marginTop: 24 },
});
