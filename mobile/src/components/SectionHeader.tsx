import { View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

/** Starts every section: a dark rule, a serif title, and an optional small note on the right. */
export function SectionHeader({ title, note }: { title: string; note?: string | null }) {
  const { colors } = useTheme();
  return (
    // If the title and note don't fit side by side (narrow phones), the note moves to its own line.
    <View style={{ borderTopWidth: 1, borderTopColor: colors.borderStrong, paddingTop: 16, paddingBottom: 12,
      flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between',
      columnGap: 12, rowGap: 4 }}>
      <Text variant="h2" accessibilityRole="header" style={{ flexShrink: 1 }}>{title}</Text>
      {note ? <Text variant="labelSmall" color="textSecondary">{note}</Text> : null}
    </View>
  );
}
