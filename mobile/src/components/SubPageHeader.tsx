import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

type Props = { back: string; label: string; title: string; intro?: string };

/**
 * Top of a screen opened from another one (like Update time from Profile): a back link,
 * a small label, the title and a short intro. On a computer a dark rule closes it off.
 */
export function SubPageHeader({ back, label, title, intro }: Props) {
  const { colors, isWide } = useTheme();
  return (
    <View style={isWide ? [styles.headerWide, { borderBottomColor: colors.borderStrong }] : styles.header}>
      <Pressable accessibilityRole="link" onPress={() => (router.canGoBack() ? router.back() : router.replace('/profile'))}
        style={styles.back}>
        <Text variant="button" color="textSecondary">← {back}</Text>
      </Pressable>
      <Text variant="labelSmall" color="textSecondary" style={styles.label}>{label}</Text>
      <Text variant="h1" accessibilityRole="header" style={styles.title}>{title}</Text>
      {intro ? (
        <Text variant="body" color="textSecondary" style={[styles.intro, isWide && styles.introWide]}>
          {intro}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  header: { marginBottom: 12 },
  headerWide: { paddingBottom: 12, marginBottom: 20, borderBottomWidth: 1 },
  back: { alignSelf: 'flex-start', paddingVertical: 4 },
  label: { marginTop: 6 },
  title: { marginTop: 4 },
  intro: { marginTop: 8 },
  introWide: { maxWidth: 480 },
});
