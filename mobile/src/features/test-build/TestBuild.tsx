/**
 * "Test build" section: pick the server and tester, or load a demo person.
 * Only for testing. Remove it once real accounts exist.
 */
import { Href, router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { ApiError, makeApi } from '../../api/client';
import { Button } from '../../components/Button';
import { LiveText } from '../../components/LiveText';
import { Text } from '../../components/Text';
import { deviceTimeZone } from '../../lib/timeZone';
import { errorText } from '../../lib/useLoad';
import { useSession } from '../../state/session';
import { useTheme } from '../../theme/theme';
import { radius, type } from '../../theme/tokens';

const DEMO = ['sam', 'alex', 'jordan'] as const;

/** Why this isn't a server address, or null if it looks fine. */
function addressProblem(address: string): string | null {
  try {
    const url = new URL(address.trim());
    if (url.protocol === 'http:' || url.protocol === 'https:') return null;
  } catch {
    // not a URL at all
  }
  return 'Type the server address with http:// at the start, like http://192.168.1.50:8000';
}

/** next: where to go once a tester is picked. */
export function TestBuild({ next = '/today' }: { next?: Href }) {
  const { colors } = useTheme();
  const session = useSession();
  const [serverUrl, setServerUrl] = useState(session.serverUrl);
  const [userId, setUserId] = useState(session.userId);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const input = [styles.input, { color: colors.textPrimary, borderColor: colors.borderStrong }];

  async function use() {
    setNote(addressProblem(serverUrl));
    if (addressProblem(serverUrl)) return;
    setBusy('use');
    try {
      const api = makeApi(serverUrl.trim(), userId.trim());
      await api.health();
      // A brand-new tester has no data yet. Saving this device's time zone creates them, so the
      // screens show "No nights yet" instead of errors, and their dates are local from the start.
      try {
        await api.settings();
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) throw e;
        await api.saveSettings({ timezone: deviceTimeZone() });
      }
      await session.update({ serverUrl: serverUrl.trim(), userId: userId.trim() });
      router.replace(next);
    } catch (e) {
      setNote(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function demo(person: (typeof DEMO)[number]) {
    setNote(addressProblem(serverUrl));
    if (addressProblem(serverUrl)) return;
    setBusy(person);
    try {
      const r = await makeApi(serverUrl, '').loadDemo(person);
      await session.update({ serverUrl: serverUrl.trim(), userId: r.user_id });
      router.replace(next);
    } catch (e) {
      setNote(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <View style={[styles.box, { borderTopColor: colors.border }]}>
      <Text variant="labelSmall" color="textMuted">Test build</Text>
      <Text variant="bodySmall" color="textSecondary" style={styles.space12}>Server address</Text>
      <TextInput value={serverUrl} onChangeText={setServerUrl} autoCapitalize="none" autoCorrect={false}
        keyboardType="url" placeholder="http://192.168.1.50:8000" placeholderTextColor={colors.textMuted}
        style={input} accessibilityLabel="Server address" />
      <Text variant="bodySmall" color="textSecondary" style={styles.space12}>Tester name</Text>
      <TextInput value={userId} onChangeText={setUserId} autoCapitalize="none" autoCorrect={false}
        placeholder="tester1" placeholderTextColor={colors.textMuted} style={input}
        accessibilityLabel="Tester name" />
      <Button title="Use this tester" kind="secondary" onPress={use} busy={busy === 'use'}
        disabled={!serverUrl.trim() || !userId.trim()} style={styles.space12} />
      <Text variant="bodySmall" color="textSecondary" style={styles.space16}>
        Or load a demo person (mock data, clock fixed at 1 Oct 2026, 8:30 am)
      </Text>
      <View style={styles.demos}>
        {DEMO.map((p) => (
          <Button key={p} title={p[0].toUpperCase() + p.slice(1)} kind="secondary" busy={busy === p}
            disabled={!serverUrl.trim()} onPress={() => demo(p)} style={styles.demo} />
        ))}
      </View>
      {note ? <LiveText error variant="bodySmall" color="low" style={styles.space12}>{note}</LiveText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { borderTopWidth: 1, paddingTop: 16, marginTop: 24 },
  input: { ...type.body, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10,
    marginTop: 6 },
  space12: { marginTop: 12 },
  space16: { marginTop: 16 },
  demos: { flexDirection: 'row', gap: 8, marginTop: 8 },
  demo: { flex: 1 },
});
