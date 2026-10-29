import { StyleSheet } from 'react-native';

import { Page } from '../../components/Page';
import { Text } from '../../components/Text';
import { headingLevel } from '../../lib/a11y';

/**
 * Figma's "Muscles, no patch sessions yet", without the body map and the Set up your patch button,
 * since patch setup comes with Layer 2.
 */
export default function MusclesScreen() {
  return (
    <Page>
      <Text variant="h1" accessibilityRole="header">Muscles</Text>
      <Text variant="greeting" accessibilityRole="header" {...headingLevel(2)} style={styles.title}>
        No patch sessions yet.
      </Text>
      <Text variant="body" color="textSecondary" style={styles.note}>
        Wear the patch during a workout to see how each muscle is recovering. Muscles you train without it show up
        here as estimates.
      </Text>
    </Page>
  );
}

const styles = StyleSheet.create({
  title: { marginTop: 28 },
  note: { marginTop: 8, maxWidth: 520 },
});
