import { Href, router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

/** home: where back goes when there's no screen to go back to (after a reload or a deep link). */
type Props = { back: string; label: string; title: string; intro?: string; home?: Href;
  /** A small line above the title, like "Tue 30 Sep · 7:05–7:40 am · Apple Watch". */
  detail?: string };

/**
 * Top of a screen opened from another one (like Update time from Profile): a back link,
 * the title and a short intro. The label isn't shown, the redesign has no small labels above titles.
 */
export function SubPageHeader({ back, title, intro, detail, home = '/profile' }: Props) {
  const { isWide } = useTheme();
  return (
    <View style={isWide ? styles.headerWide : styles.header}>
      <Pressable accessibilityRole="link" accessibilityLabel={`Back to ${back}`}
        onPress={() => (router.canGoBack() ? router.back() : router.replace(home))} style={styles.back}>
        <Text variant="button" color="textSecondary">‹ {back}</Text>
      </Pressable>
      {detail ? <Text variant="bodySmall" color="textSecondary" style={styles.detail}>{detail}</Text> : null}
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
  detail: { marginTop: 6 },
  headerWide: { paddingBottom: 12, marginBottom: 20 },
  back: { alignSelf: 'flex-start', minHeight: 44, justifyContent: 'center' },
  title: { marginTop: 4 },
  intro: { marginTop: 8 },
  introWide: { maxWidth: 480 },
});
