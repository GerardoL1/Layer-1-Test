/**
 * Tab bar (iPhone) and Sidebar (computer) from Figma. Both are text only:
 * the current tab gets a short dark bar on the rule above it, the current page
 * a dark bar on its left edge.
 */
import { Href, Link, usePathname } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { currentPage } from '../lib/a11y';
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
    <View style={[styles.tabBar, { borderTopColor: colors.borderStrong, paddingBottom: Math.max(insets.bottom, 12),
      backgroundColor: colors.canvas }]}>
      {TABS.map((tab) => {
        const active = path.startsWith(tab.path);
        return (
          <Link key={tab.path} href={tab.href} asChild>
            <Pressable accessibilityRole="link" {...currentPage(active)} style={styles.tab}>
              <View style={[styles.tabMark, { backgroundColor: active ? colors.borderStrong : 'transparent' }]} />
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
    <View style={[styles.sidebar, { borderRightColor: colors.borderStrong }]}>
      <Text variant="h1" style={styles.brand}>Recovery</Text>
      {TABS.map((tab) => {
        const active = path.startsWith(tab.path);
        return (
          <Link key={tab.path} href={tab.href} asChild>
            <Pressable accessibilityRole="link" {...currentPage(active)}
              style={StyleSheet.flatten([styles.link, { borderLeftColor: active ? colors.borderStrong : 'transparent' }])}>
              <Text variant={active ? 'bodyEmphasis' : 'body'} color={active ? 'textPrimary' : 'textSecondary'}>
                {tab.label}
              </Text>
            </Pressable>
          </Link>
        );
      })}
      <View style={styles.spacer} />
      {footer ? <Text variant="bodySmall" color="textSecondary">{footer}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  tabBar: { borderTopWidth: 1, flexDirection: 'row' },
  tab: { flex: 1, alignItems: 'center', paddingTop: 16 },
  tabMark: { position: 'absolute', top: -1, height: 3, width: 32 },
  sidebar: { width: 232, borderRightWidth: 1, paddingTop: 40, paddingHorizontal: 24, paddingBottom: 24 },
  brand: { fontSize: 28, marginBottom: 40 },
  link: { paddingVertical: 10, paddingLeft: 14, borderLeftWidth: 2, marginBottom: 6 },
  spacer: { flex: 1 },
});
