import { StyleSheet } from 'react-native';

import { Page } from '../../components/Page';
import { Text } from '../../components/Text';

export default function TrainScreen() {
  return (
    <Page>
      <Text variant="h1">Train</Text>
      <Text color="textSecondary" style={styles.note}>Training plans come after the readiness score is decided.</Text>
    </Page>
  );
}

const styles = StyleSheet.create({
  note: { marginTop: 12 },
});
