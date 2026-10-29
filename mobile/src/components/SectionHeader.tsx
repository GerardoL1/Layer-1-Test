import { StyleSheet, View } from 'react-native';

import { Text } from './Text';

/** Starts every section: a title in sentence case at reading size, and an optional small note on the right. */
export function SectionHeader({ title, note }: { title: string; note?: string | null }) {
  return (
    // If the title and note don't fit side by side (narrow phones), the note moves to its own line.
    <View style={styles.header}>
      <Text variant="h3" accessibilityRole="header" style={styles.title}>{title}</Text>
      {note ? <Text variant="bodySmall" color="textSecondary">{note}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingTop: 16, paddingBottom: 12, flexDirection: 'row', flexWrap: 'wrap',
    alignItems: 'baseline', justifyContent: 'space-between', columnGap: 12, rowGap: 4 },
  title: { flexShrink: 1 },
});
