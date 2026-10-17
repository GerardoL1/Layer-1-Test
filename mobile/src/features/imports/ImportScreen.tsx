/**
 * Profile > Your data > Import Apple Health export (computer view).
 */
import { router } from 'expo-router';
import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { Button } from '../../components/Button';
import { DropZone } from '../../components/DropZone';
import { ListRow } from '../../components/ListRow';
import { NumberedSteps } from '../../components/NumberedSteps';
import { Page } from '../../components/Page';
import { ProgressBar } from '../../components/ProgressBar';
import { SectionHeader } from '../../components/SectionHeader';
import { SubPageHeader } from '../../components/SubPageHeader';
import { Text } from '../../components/Text';
import { canPickFile } from '../../lib/pickFile';
import { useTheme } from '../../theme/theme';
import { importProgress, useImportJob } from './useImportJob';

const STEPS = [
  'Open Health, tap your picture (top right), then Export All Health Data.',
  'Tap Export and wait. Large histories can take a few minutes.',
  'Send export.zip to this computer (AirDrop, email or iCloud Drive).',
];

const thousands = (n: number) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const count = (n: number, one: string, many: string) => `${thousands(n)} ${n === 1 ? one : many}`;
const fileSize = (bytes: number) => (bytes >= 1e6 ? `${Math.round(bytes / 1e6)} MB` : `${Math.max(1, Math.round(bytes / 1e3))} KB`);

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <View style={styles.section}>
      <SectionHeader title={title} note={note} />
      {children}
    </View>
  );
}

export default function ImportScreen() {
  const { colors, isWide } = useTheme();
  const { job, start, busy, done } = useImportJob({ resume: true });
  const counts = job?.status?.counts ?? {};
  const p = job ? importProgress(job) : null;
  const problem = job?.error ?? job?.status?.error;

  const onIphone = (
    <Section title="On your iPhone" note="2 minutes">
      <NumberedSteps steps={STEPS} />
    </Section>
  );

  const upload = (
    <View>
      <Section title="Upload" note="export.zip or export.xml">
        {canPickFile ? (
          // Problems show in the Importing section, so nothing else to do with them here.
          <DropZone onFile={(file) => start(file).catch(() => {})} disabled={busy}
            note="Files up to 2 GB. Re-importing the same file is safe, duplicates are skipped." />
        ) : (
          <Text color="textSecondary">Importing a file works on the computer view. On iPhone, data comes from Apple Health.</Text>
        )}
      </Section>
      {job && p ? (
        <Section title={problem ? 'Import failed' : done ? 'Imported' : 'Importing'} note={`${job.name} · ${fileSize(job.bytes)}`}>
          <View style={styles.bar}>
            <ProgressBar share={p.share} />
          </View>
          <Text variant="labelSmall" color="textMuted" style={styles.phase}>
            {Math.round(p.share * 100)}% · {p.phase}
          </Text>
          <ListRow label="Heart rate" value={count(counts.heart_rate ?? 0, 'reading', 'readings')} />
          <ListRow label="HRV" value={count(counts.hrv_sdnn ?? 0, 'reading', 'readings')} />
          <ListRow label="Sleep" value={count(counts.sleep_stages ?? 0, 'piece', 'pieces')} />
          <ListRow label="Nights ready" value={done ? count(job.status?.nights_ready ?? 0, 'night', 'nights') : 'After the import'} />
          <View style={[styles.rule, { borderTopColor: colors.border }]} />
          {problem ? <Text variant="bodySmall" color="low" style={styles.problem}>{problem}</Text> : null}
          {done ? <Button title="Go to Today" style={styles.goToday} onPress={() => router.replace('/today')} /> : null}
        </Section>
      ) : null}
    </View>
  );

  return (
    <Page>
      <SubPageHeader back="Profile" label="Your data" title="Import an Apple Health export"
        intro="Bring in past nights from the Health app on your iPhone. We keep only heart rate, resting heart rate, HRV and sleep. Everything else in the file is ignored." />
      {isWide ? (
        <View style={styles.columns}>
          <View style={styles.column}>{onIphone}</View>
          <View style={styles.column}>{upload}</View>
        </View>
      ) : (
        <>
          {onIphone}
          {upload}
        </>
      )}
    </Page>
  );
}

const styles = StyleSheet.create({
  section: { marginBottom: 24 },
  bar: { marginTop: 4 },
  phase: { marginTop: 8, marginBottom: 4 },
  rule: { borderTopWidth: 1 },
  problem: { marginTop: 10 },
  goToday: { alignSelf: 'flex-start', marginTop: 16 },
  columns: { flexDirection: 'row', gap: 56 },
  column: { flex: 1 },
});
