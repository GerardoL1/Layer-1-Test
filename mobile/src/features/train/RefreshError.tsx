import { StyleSheet } from 'react-native';

import { LiveText } from '../../components/LiveText';

/**
 * Shown above data that's still on screen from before when loading it again failed (the server went away,
 * or the tester changed). Without it the old data would look current and nobody would hear about the error.
 */
export function RefreshError({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <LiveText error variant="bodySmall" color="low" style={styles.error}>
      {`Couldn't refresh, this may be out of date. ${error}`}
    </LiveText>
  );
}

const styles = StyleSheet.create({
  error: { marginBottom: 12 },
});
