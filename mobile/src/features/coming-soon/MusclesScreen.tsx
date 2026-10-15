import { StyleSheet } from 'react-native';

import { Page } from '../../components/Page';
import { Text } from '../../components/Text';

export default function MusclesScreen() {
  return (
    <Page>
      <Text variant="h1">Muscles</Text>
      <Text color="textSecondary" style={styles.note}>Muscle-specific fatigue comes with Layer 2 (sEMG patch).</Text>
    </Page>
  );
}

const styles = StyleSheet.create({
  note: { marginTop: 12 },
});
