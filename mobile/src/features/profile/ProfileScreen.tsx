import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { ListRow } from '../../components/ListRow';
import { Panel } from '../../components/Panel';
import { Page, PageState } from '../../components/Page';
import { Text } from '../../components/Text';
import { displayName, longDate } from '../../lib/format';
import { useLoad } from '../../lib/useLoad';
import { useSession } from '../../state/session';
import { useTheme } from '../../theme/theme';
import { TestBuild } from '../test-build/TestBuild';
import { ProfileData } from './ProfileData';
import { ProfileSettings } from './ProfileSettings';

export default function ProfileScreen() {
  const api = useApi();
  const session = useSession();
  const { isWide } = useTheme();
  const { data: p, error, loading, reload } = useLoad(() => api.profile(), api);

  // Switching tester or server has to work even when Profile can't load (server down, wrong
  // address, or a tester with no data yet), or there'd be no way out of this screen.
  const testerTools = (
    <View style={styles.space24}>
      <Panel>
        <ListRow label="Switch tester" onPress={async () => {
          await session.signOut();
          router.replace('/setup');
        }} />
      </Panel>
      <TestBuild />
    </View>
  );

  if (!p) {
    return (
      <Page>
        <PageState loading={loading} error={error} />
        {error ? (
          <>
            <Button title="Try again" kind="secondary" onPress={reload} style={styles.retry} />
            {testerTools}
          </>
        ) : null}
      </Page>
    );
  }
  const left = <ProfileData profile={p} reload={reload} />;
  const right = <ProfileSettings settings={p.settings} reload={reload} />;

  return (
    <Page>
      <Text variant="h1" accessibilityRole="header">{displayName(p.user_id)}</Text>
      <Text variant="body" color="textSecondary" style={styles.since}>
        {p.first_night
          ? `Tracking since ${longDate(p.first_night)} · ${p.nights_usable} ${p.nights_usable === 1 ? 'night' : 'nights'} recorded`
          : 'No nights yet'}
      </Text>
      {isWide ? (
        <View style={styles.columns}>
          <View style={styles.column}>{left}</View>
          <View style={styles.column}>{right}</View>
        </View>
      ) : (
        <>
          {left}
          <View style={styles.space32}>{right}</View>
        </>
      )}
      {testerTools}
      <Text variant="bodySmall" color="textMuted" style={styles.footer}>
        Readiness is a training guide, not medical advice. Version 0.1 (test build).
      </Text>
    </Page>
  );
}

const styles = StyleSheet.create({
  since: { marginTop: 4, marginBottom: 24 },
  columns: { flexDirection: 'row', gap: 56 },
  column: { flex: 1 },
  space32: { marginTop: 32 },
  space24: { marginTop: 24 },
  retry: { alignSelf: 'flex-start', marginTop: 16 },
  footer: { marginTop: 24 },
});
