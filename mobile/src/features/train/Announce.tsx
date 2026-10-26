import { StyleSheet } from 'react-native';

import { LiveText } from '../../components/LiveText';

/**
 * Says a short message to screen readers without showing it, for screens that change step in place
 * (like the Nix import going from "Add sweat data" to "Check your import"). Sighted people see the new title.
 */
export function Announce({ text }: { text: string }) {
  return <LiveText style={styles.hidden}>{text}</LiveText>;
}

const styles = StyleSheet.create({
  // Kept in the page for screen readers, but takes no space and can't be seen.
  hidden: { position: 'absolute', width: 1, height: 1, overflow: 'hidden', opacity: 0 },
});
