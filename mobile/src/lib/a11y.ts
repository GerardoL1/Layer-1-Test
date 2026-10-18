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
