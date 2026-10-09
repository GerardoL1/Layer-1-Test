import { Page } from '../../components/Page';
import { Text } from '../../components/Text';

export default function TrainScreen() {
  return (
    <Page>
      <Text variant="h1">Train</Text>
      <Text color="textSecondary" style={{ marginTop: 12 }}>Training plans come after the readiness score is decided.</Text>
    </Page>
  );
}
