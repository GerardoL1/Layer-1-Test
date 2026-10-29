import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { Button } from '../../components/Button';
import { LiveText } from '../../components/LiveText';
import { useTheme } from '../../theme/theme';

/**
 * Loading and couldn't-load for the Train screens, like Figma's "loading" and "couldn't load" frames:
 * a spinner, or the server's message in red with a Try again button.
 */
export function LoadState({ loading, error, onRetry }: { loading: boolean; error: string | null; onRetry: () => void }) {
  const { colors } = useTheme();
  if (error) {
    return (
      <View style={styles.state}>
        <LiveText error color="low">{error}</LiveText>
        <Button title="Try again" onPress={onRetry} />
      </View>
    );
  }
  if (loading) return <ActivityIndicator accessibilityLabel="Loading" color={colors.textSecondary} style={styles.state} />;
  return null;
}

const styles = StyleSheet.create({
  state: { marginTop: 24, gap: 16, alignSelf: 'stretch' },
});
