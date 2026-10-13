import { router } from 'expo-router';
import { Pressable, View } from 'react-native';

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
    <View style={isWide ? { paddingBottom: 12, marginBottom: 20, borderBottomWidth: 1,
      borderBottomColor: colors.borderStrong } : { marginBottom: 12 }}>
      <Pressable accessibilityRole="link" onPress={() => (router.canGoBack() ? router.back() : router.replace('/profile'))}
        style={{ alignSelf: 'flex-start', paddingVertical: 4 }}>
        <Text variant="button" color="textSecondary">← {back}</Text>
      </Pressable>
      <Text variant="labelSmall" color="textSecondary" style={{ marginTop: 6 }}>{label}</Text>
      <Text variant="h1" accessibilityRole="header" style={{ marginTop: 4 }}>{title}</Text>
      {intro ? (
        <Text variant="body" color="textSecondary" style={{ marginTop: 8, maxWidth: isWide ? 480 : undefined }}>
          {intro}
        </Text>
      ) : null}
    </View>
  );
}
