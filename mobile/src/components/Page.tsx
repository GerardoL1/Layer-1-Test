import { ReactNode } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { LiveText } from './LiveText';
import { Text } from './Text';

/**
 * Scrolling page with the side margins from Figma (20 on iPhone, 48 on a computer).
 * form: a page with text boxes. A tap on a button then works while the keyboard is up,
 * instead of only closing the keyboard.
 */
export function Page({ children, form }: { children: ReactNode; form?: boolean }) {
  const { colors, isWide } = useTheme();
  return (
    <ScrollView role="main" style={[styles.page, { backgroundColor: colors.canvas }]}
      keyboardShouldPersistTaps={form ? 'handled' : undefined}
      contentContainerStyle={isWide ? styles.contentWide : styles.content}>
      <View style={[styles.column, isWide && styles.columnWide]}>{children}</View>
    </ScrollView>
  );
}

/** Shown while a page loads or when the server can't be reached. */
export function PageState({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) {
    return (
      <View style={styles.state}>
        <Text variant="h3" accessibilityRole="header">{"Couldn't load this page"}</Text>
        <LiveText error color="low">{error}</LiveText>
      </View>
    );
  }
  if (loading) return <LiveText color="textMuted" style={styles.state}>Loading…</LiveText>;
  return null;
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  content: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 40 },
  contentWide: { paddingHorizontal: 48, paddingTop: 40, paddingBottom: 40 },
  column: { width: '100%', alignSelf: 'center' },
  columnWide: { maxWidth: 1112 },
  state: { marginTop: 24, gap: 6 },
});
