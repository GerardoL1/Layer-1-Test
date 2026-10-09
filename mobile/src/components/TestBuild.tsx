/**
 * "Test build" section: pick the server and tester, or load a demo person.
 * Only for testing. Remove it once real accounts exist.
 */
import { router } from 'expo-router';
import { useState } from 'react';
import { TextInput, View } from 'react-native';

import { makeApi } from '../api/client';
import { useSession } from '../state/session';
import { useTheme } from '../theme/theme';
import { radius, type } from '../theme/tokens';
import { Button } from './Button';
import { Text } from './Text';

const DEMO = ['sam', 'alex', 'jordan'] as const;

export function TestBuild() {
  const { colors } = useTheme();
  const session = useSession();
  const [serverUrl, setServerUrl] = useState(session.serverUrl);
  const [userId, setUserId] = useState(session.userId);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const input = {
    ...type.body, color: colors.textPrimary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10, marginTop: 6,
  };

  async function use() {
    setBusy('use');
    setNote(null);
    try {
      await makeApi(serverUrl, userId).health();
      await session.update({ serverUrl: serverUrl.trim(), userId: userId.trim() });
      router.replace('/today');
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
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
      router.replace('/today');
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <View style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 16, marginTop: 24 }}>
      <Text variant="labelSmall" color="textMuted">Test build</Text>
      <Text variant="bodySmall" color="textSecondary" style={{ marginTop: 12 }}>Server address</Text>
      <TextInput value={serverUrl} onChangeText={setServerUrl} autoCapitalize="none" autoCorrect={false}
        keyboardType="url" placeholder="http://192.168.1.50:8000" placeholderTextColor={colors.textMuted}
        style={input} accessibilityLabel="Server address" />
      <Text variant="bodySmall" color="textSecondary" style={{ marginTop: 12 }}>Tester name</Text>
      <TextInput value={userId} onChangeText={setUserId} autoCapitalize="none" autoCorrect={false}
        placeholder="tester1" placeholderTextColor={colors.textMuted} style={input}
        accessibilityLabel="Tester name" />
      <Button title="Use this tester" kind="secondary" onPress={use} busy={busy === 'use'}
        disabled={!serverUrl.trim() || !userId.trim()} style={{ marginTop: 12 }} />
      <Text variant="bodySmall" color="textSecondary" style={{ marginTop: 16 }}>
        Or load a demo person (mock data, clock fixed at 1 Oct 2026, 8:30 am)
      </Text>
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
        {DEMO.map((p) => (
          <Button key={p} title={p[0].toUpperCase() + p.slice(1)} kind="secondary" busy={busy === p}
            disabled={!serverUrl.trim()} onPress={() => demo(p)} style={{ flex: 1 }} />
        ))}
      </View>
      {note ? <Text variant="bodySmall" color="low" style={{ marginTop: 12 }}>{note}</Text> : null}
    </View>
  );
}
