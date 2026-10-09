/**
 * Tab bar (iPhone) and Sidebar (computer) from Figma. Both are text only:
 * the current tab gets a short dark bar on the rule above it, the current page
 * a dark bar on its left edge.
 */
import { Href, Link, usePathname } from 'expo-router';
import { Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

export const TABS: { href: Href; path: string; label: string }[] = [
  { href: '/today', path: '/today', label: 'Today' },
  { href: '/muscles', path: '/muscles', label: 'Muscles' },
  { href: '/train', path: '/train', label: 'Train' },
  { href: '/trends', path: '/trends', label: 'Trends' },
  { href: '/profile', path: '/profile', label: 'Profile' },
];

export function TabBar() {
  const { colors } = useTheme();
  const path = usePathname();
  const insets = useSafeAreaInsets();
  return (
    <View style={{ borderTopWidth: 1, borderTopColor: colors.borderStrong, flexDirection: 'row',
      paddingBottom: Math.max(insets.bottom, 12), backgroundColor: colors.canvas }}>
      {TABS.map((tab) => {
        const active = path.startsWith(tab.path);
        return (
          <Link key={tab.path} href={tab.href} asChild>
            <Pressable accessibilityRole="tab" accessibilityState={{ selected: active }}
              style={{ flex: 1, alignItems: 'center', paddingTop: 16 }}>
              <View style={{ position: 'absolute', top: -1, height: 3, width: 32,
                backgroundColor: active ? colors.borderStrong : 'transparent' }} />
              <Text variant="labelSmall" color={active ? 'textPrimary' : 'textMuted'}>{tab.label}</Text>
            </Pressable>
          </Link>
        );
      })}
    </View>
  );
}

export function Sidebar({ footer }: { footer?: string | null }) {
  const { colors } = useTheme();
  const path = usePathname();
  return (
    <View style={{ width: 232, borderRightWidth: 1, borderRightColor: colors.borderStrong,
      paddingTop: 40, paddingHorizontal: 24, paddingBottom: 24 }}>
      <Text variant="h1" style={{ fontSize: 28, marginBottom: 40 }}>Recovery</Text>
      {TABS.map((tab) => {
        const active = path.startsWith(tab.path);
        return (
          <Link key={tab.path} href={tab.href} asChild>
            <Pressable accessibilityRole="link" accessibilityState={{ selected: active }}
              style={{ paddingVertical: 10, paddingLeft: 14, borderLeftWidth: 2, marginBottom: 6,
                borderLeftColor: active ? colors.borderStrong : 'transparent' }}>
              <Text variant={active ? 'bodyEmphasis' : 'body'} color={active ? 'textPrimary' : 'textSecondary'}>
                {tab.label}
              </Text>
            </Pressable>
          </Link>
        );
      })}
      <View style={{ flex: 1 }} />
      {footer ? <Text variant="bodySmall" color="textSecondary">{footer}</Text> : null}
    </View>
  );
}
