/**
 * "Test build" section: pick the server and tester, or load a demo person.
 * Only for testing. Remove it once real accounts exist.
 */
import { Href, router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { makeApi } from '../../api/client';
import { Button } from '../../components/Button';
import { Text } from '../../components/Text';
import { errorText } from '../../lib/useLoad';
import { useSession } from '../../state/session';
import { useTheme } from '../../theme/theme';
import { radius, type } from '../../theme/tokens';

const DEMO = ['sam', 'alex', 'jordan'] as const;

/** next: where to go once a tester is picked. */
export function TestBuild({ next = '/today' }: { next?: Href }) {
  const { colors } = useTheme();
  const session = useSession();
  const [serverUrl, setServerUrl] = useState(session.serverUrl);
  const [userId, setUserId] = useState(session.userId);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const input = [styles.input, { color: colors.textPrimary, borderColor: colors.border }];

  async function use() {
    setBusy('use');
    setNote(null);
    try {
      await makeApi(serverUrl, userId).health();
      await session.update({ serverUrl: serverUrl.trim(), userId: userId.trim() });
      router.replace(next);
    } catch (e) {
      setNote(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function demo(person: (typeof DEMO)[number]) {
    setBusy(person);
    setNote(null);
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
      {note ? <Text variant="bodySmall" color="low" style={styles.space12}>{note}</Text> : null}
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
