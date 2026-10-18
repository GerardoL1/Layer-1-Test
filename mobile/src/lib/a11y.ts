/** Small accessibility helpers shared by the components. */
import { AccessibilityInfo, Platform } from 'react-native';

/**
 * Marks the link to the page you're on. On the web that's aria-current, which React Native's types
 * don't list but react-native-web passes through ("current page"). On iPhone it's the selected state.
 */
export function currentPage(active: boolean): Record<string, string | boolean> {
  if (Platform.OS !== 'web') return { 'aria-selected': active };
  return active ? { 'aria-current': 'page' } : {};
}

/**
 * Reads a message out on iPhone. iOS ignores live regions, so status changes like
 * "Imported" have to be announced. Android and the web use aria-live on the text instead.
 */
export function announce(message: string | null | undefined) {
  if (message && Platform.OS === 'ios') AccessibilityInfo.announceForAccessibility(message);
}

/**
 * Heading level on the web. react-native-web makes every header an h1 unless told otherwise,
 * which flattens the page outline. Native platforms have no levels, so nothing is added there.
 */
export function headingLevel(level: number | undefined): Record<string, number> {
  return Platform.OS === 'web' && level ? { 'aria-level': level } : {};
}

const PAGE_TITLES: [string, string][] = [
  ['/profile/update-time', 'Update time'],
  ['/profile/import', 'Import'],
  ['/profile', 'Profile'],
  ['/today', 'Today'],
  ['/trends', 'Trends'],
  ['/muscles', 'Muscles'],
  ['/train', 'Train'],
  ['/setup', 'Setup'],
  ['/components', 'Components'],
];

/** The browser tab title for a path, so each page says where you are ("Trends · Recovery"). */
export function pageTitle(path: string): string {
  const page = PAGE_TITLES.find(([prefix]) => path.startsWith(prefix))?.[1];
  return page ? `${page} · Recovery` : 'Recovery';
}
