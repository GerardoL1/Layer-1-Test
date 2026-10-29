import { StyleSheet, View } from 'react-native';

import { useTheme } from '../theme/theme';
import { Text } from './Text';

/** A short numbered list, like "How it works". */
export function NumberedSteps({ steps }: { steps: string[] }) {
  const { colors } = useTheme();
  return (
    <>
      {steps.map((s, i) => (
        <View key={i} style={[styles.step, { borderTopColor: colors.border }]}>
          <Text variant="scoreMetric" style={styles.number}>{i + 1}</Text>
          <Text variant="body" style={styles.text}>{s}</Text>
        </View>
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  step: { flexDirection: 'row', gap: 14, paddingVertical: 14 },
  number: { fontSize: 24, lineHeight: 26, width: 16 },
  text: { flex: 1 },
});
