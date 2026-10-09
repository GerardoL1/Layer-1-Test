import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { ListRow } from '../../components/ListRow';
import { SetupFrame } from '../../components/SetupFrame';
import { Text } from '../../components/Text';
import { connectHealth, healthAvailable, sendLastDay } from '../../health/health';
import { canPickFile, pickFile } from '../../lib/pickFile';
import { useSession } from '../../state/session';

const READS = [
  { label: 'Heart rate variability', when: 'Overnight' },
  { label: 'Resting heart rate', when: 'Overnight' },
  { label: 'Heart rate', when: 'During sleep' },
  { label: 'Sleep stages', when: 'Every night' },
];

/** Setup 2: Connect Apple Health on iPhone, or import a Health export on a computer. */
export default function HealthStep() {
  const api = useApi();
  const { serverUrl, userId } = useSession();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const phone = healthAvailable();

  async function connect() {
    setBusy(true);
    setNote(null);
    try {
      await connectHealth();
      setNote(await sendLastDay(serverUrl, userId));
      router.push('/setup/about');
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importFile() {
    const file = await pickFile('.zip,.xml');
    if (!file) return;
    setBusy(true);
    setNote(`Uploading ${file.name}…`);
    try {
      await api.importExport(file, file.name);
      for (;;) {
        await new Promise((r) => setTimeout(r, 2000));
        const s = await api.importStatus();
        if (s.state === 'done') break;
        if (s.state === 'error') throw new Error(`Import failed: ${s.error}`);
        setNote(s.state === 'processing' ? 'Working out your nights…' : 'Reading the export…');
      }
      router.push('/setup/about');
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SetupFrame step={1} actions={
      <>
        {phone ? <Button title="Connect Apple Health" busy={busy} onPress={connect} /> : null}
        {!phone && canPickFile ? <Button title="Import Apple Health export" busy={busy} onPress={importFile} /> : null}
        <Button title={phone ? 'Skip for now' : 'Continue without importing'} kind="secondary"
          onPress={() => router.push('/setup/about')} />
        {note ? <Text variant="bodySmall" color="textSecondary">{note}</Text> : null}
        <Text variant="bodySmall" color="textMuted">
          {phone ? 'Next, iPhone will ask which data to share. Turn on all four.'
            : 'On a computer, export from the iPhone: Health > profile picture > Export All Health Data, then pick the export.zip here.'}
        </Text>
      </>
    }>
      <Text variant="h1" accessibilityRole="header">{phone ? 'Connect Apple Health' : 'Bring in your Apple Health data'}</Text>
      <Text variant="bodyLarge" color="textSecondary" style={{ marginTop: 12 }}>
        Your watch saves these to the Health app while you sleep. We read them once a day, on your phone.
      </Text>
      <View style={{ marginTop: 20 }}>
        {READS.map((r) => <ListRow key={r.label} label={r.label} value={r.when} />)}
      </View>
      <Text variant="bodySmall" color="textMuted" style={{ marginTop: 16 }}>
        We don&apos;t read your location, workouts or anything else. You can turn access off any time in the Health app.
      </Text>
    </SetupFrame>
  );
}
