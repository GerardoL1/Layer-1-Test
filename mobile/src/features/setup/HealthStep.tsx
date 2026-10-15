import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Button } from '../../components/Button';
import { ListRow } from '../../components/ListRow';
import { SetupFrame } from '../../components/SetupFrame';
import { Text } from '../../components/Text';
import { connectHealth, healthAvailable, syncHealth } from '../../health/health';
import { canPickFile, pickFile } from '../../lib/pickFile';
import { errorText } from '../../lib/useLoad';
import { useSession } from '../../state/session';
import { useImportJob } from '../imports/useImportJob';

const READS = [
  { label: 'Heart rate variability', when: 'Overnight' },
  { label: 'Resting heart rate', when: 'Overnight' },
  { label: 'Heart rate', when: 'During sleep' },
  { label: 'Sleep stages', when: 'Every night' },
];

/** Setup 2: Connect Apple Health on iPhone, or import a Health export on a computer. */
export default function HealthStep() {
  const { serverUrl, userId } = useSession();
  const importJob = useImportJob({ pollMs: 2000 });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const phone = healthAvailable();

  async function connect() {
    setBusy(true);
    setNote(null);
    try {
      await connectHealth();
      setNote('Reading the last 90 days from Apple Health…');
      const r = await syncHealth(serverUrl, userId);
      setNote(r.message);
      router.push('/setup/about');
    } catch (e) {
      setNote(errorText(e));
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
      await importJob.start(file);
      router.push('/setup/about');
    } catch (e) {
      setNote(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  // While importing, say what the server is doing once it has started.
  const status = importJob.job?.status;
  const shown = busy && status
    ? (status.state === 'processing' ? 'Working out your nights…' : 'Reading the export…')
    : note;

  return (
    <SetupFrame step={1} actions={
      <>
        {phone ? <Button title="Connect Apple Health" busy={busy} onPress={connect} /> : null}
        {!phone && canPickFile ? <Button title="Import Apple Health export" busy={busy} onPress={importFile} /> : null}
        <Button title={phone ? 'Skip for now' : 'Continue without importing'} kind="secondary"
          onPress={() => router.push('/setup/about')} />
        {shown ? <Text variant="bodySmall" color="textSecondary">{shown}</Text> : null}
        <Text variant="bodySmall" color="textMuted">
          {phone ? 'Next, iPhone will ask which data to share. Turn on all four.'
            : 'On a computer, export from the iPhone: Health > profile picture > Export All Health Data, then pick the export.zip here.'}
        </Text>
      </>
    }>
      <Text variant="h1" accessibilityRole="header">{phone ? 'Connect Apple Health' : 'Bring in your Apple Health data'}</Text>
      <Text variant="bodyLarge" color="textSecondary" style={styles.intro}>
        Your watch saves these to the Health app while you sleep. We read them once a day, on your phone.
      </Text>
      <View style={styles.reads}>
        {READS.map((r) => <ListRow key={r.label} label={r.label} value={r.when} />)}
      </View>
      <Text variant="bodySmall" color="textMuted" style={styles.privacy}>
        We don&apos;t read your location, workouts or anything else. You can turn access off any time in the Health app.
      </Text>
    </SetupFrame>
  );
}

const styles = StyleSheet.create({
  intro: { marginTop: 12 },
  reads: { marginTop: 20 },
  privacy: { marginTop: 16 },
});
