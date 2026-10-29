import { ReactNode } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Button } from './Button';
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

/**
 * Shown while a page loads (a spinner) or when the server can't be reached.
 * onRetry adds a Try again button, the page's only action then, so it's primary.
 */
export function PageState({ loading, error, onRetry }: { loading: boolean; error: string | null; onRetry?: () => void }) {
  const { colors } = useTheme();
  if (error) {
    return (
      <View style={styles.state}>
        <Text variant="h3" accessibilityRole="header">{"Couldn't load this page"}</Text>
        <LiveText error color="low">{error}</LiveText>
        {onRetry ? <Button title="Try again" onPress={onRetry} style={styles.retry} /> : null}
      </View>
    );
  }
  if (loading) return <ActivityIndicator accessibilityLabel="Loading" color={colors.textSecondary} style={styles.state} />;
  return null;
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  content: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 40 },
  contentWide: { paddingHorizontal: 48, paddingTop: 40, paddingBottom: 40 },
  column: { width: '100%', alignSelf: 'center' },
  columnWide: { maxWidth: 1112 },
  state: { marginTop: 24, gap: 6 },
  retry: { marginTop: 10 },
});
