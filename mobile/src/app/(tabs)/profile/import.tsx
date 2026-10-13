/**
 * Profile > Your data > Import Apple Health export (computer view).
 * The bar covers the whole job: sending the file (first 20%), the server reading it (to 95%),
 * then working out the nights.
 */
import { router } from 'expo-router';
import { ReactNode, useEffect, useRef, useState } from 'react';
import { View } from 'react-native';

import { ImportStatus } from '../../../api/client';
import { useApi } from '../../../api/useApi';
import { Button } from '../../../components/Button';
import { DropZone } from '../../../components/DropZone';
import { ListRow } from '../../../components/ListRow';
import { Page } from '../../../components/Page';
import { ProgressBar } from '../../../components/ProgressBar';
import { SectionHeader } from '../../../components/SectionHeader';
import { SubPageHeader } from '../../../components/SubPageHeader';
import { Text } from '../../../components/Text';
import { canPickFile } from '../../../lib/pickFile';
import { useSession } from '../../../state/session';
import { useTheme } from '../../../theme/theme';

const MAX_BYTES = 2 * 1024 ** 3;
const STEPS = [
  'Open Health, tap your picture (top right), then Export All Health Data.',
  'Tap Export and wait. Large histories can take a few minutes.',
  'Send export.zip to this computer (AirDrop, email or iCloud Drive).',
];

const thousands = (n: number) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const fileSize = (bytes: number) => (bytes >= 1e6 ? `${Math.round(bytes / 1e6)} MB` : `${Math.max(1, Math.round(bytes / 1e3))} KB`);

type Job = { name: string; bytes: number; sent: number; status: ImportStatus | null; error: string | null };

function progress(job: Job): { share: number; phase: string } {
  const s = job.status;
  if (job.error || s?.state === 'error') return { share: 0, phase: 'Import failed' };
  if (!s || s.state === 'idle') return { share: job.sent * 0.2, phase: 'Uploading' };
  if (s.state === 'queued') return { share: 0.2, phase: 'Reading the export' };
  if (s.state === 'running') {
    const what = s.reading && s.reading !== 'done' ? `${s.reading} records` : 'the export';
    return { share: 0.2 + (s.read_fraction ?? 0) * 0.75, phase: `Reading ${what}` };
  }
  if (s.state === 'processing') return { share: 0.95, phase: 'Working out your nights' };
  return { share: 1, phase: 'Done' };
}

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <View style={{ marginBottom: 24 }}>
      <SectionHeader title={title} note={note} />
      {children}
    </View>
  );
}

export default function ImportScreen() {
  const api = useApi();
  const { userId } = useSession();
  const { colors, isWide } = useTheme();
  const [job, setJob] = useState<Job | null>(null);
  const polling = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (polling.current) clearInterval(polling.current);
    polling.current = null;
  };

  function poll() {
    stopPolling();
    polling.current = setInterval(async () => {
      try {
        const s = await api.importStatus();
        setJob((j) => (j ? { ...j, status: s } : j));
        if (s.state === 'done' || s.state === 'error') stopPolling();
      } catch (e) {
        setJob((j) => (j ? { ...j, error: e instanceof Error ? e.message : String(e) } : j));
        stopPolling();
      }
    }, 1000);
  }

  // Reopening the screen during an import picks it up again.
  useEffect(() => {
    let alive = true;
    api.importStatus().then((s) => {
      if (alive && s.user_id === userId && ['queued', 'running', 'processing'].includes(s.state)) {
        setJob({ name: s.file_name ?? 'export.zip', bytes: s.file_bytes ?? 0, sent: 1, status: s, error: null });
        poll();
      }
    }).catch(() => {});
    return () => {
      alive = false;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, userId]);

  async function start(file: File) {
    if (file.size > MAX_BYTES) {
      setJob({ name: file.name, bytes: file.size, sent: 0, status: null,
        error: 'That file is over 2 GB. Unzip it and pick export.xml, or use import_export.py on the server.' });
      return;
    }
    setJob({ name: file.name, bytes: file.size, sent: 0, status: null, error: null });
    try {
      await api.importExport(file, file.name, (share) => setJob((j) => (j ? { ...j, sent: share } : j)));
      setJob((j) => (j ? { ...j, sent: 1 } : j));
      poll();
    } catch (e) {
      setJob((j) => (j ? { ...j, error: e instanceof Error ? e.message : String(e) } : j));
    }
  }

  const busy = !!job && !job.error && job.status?.state !== 'done' && job.status?.state !== 'error';
  const done = job?.status?.state === 'done';
  const counts = job?.status?.counts ?? {};
  const p = job ? progress(job) : null;

  const onIphone = (
    <Section title="On your iPhone" note="2 minutes">
      {STEPS.map((s, i) => (
        <View key={i} style={{ flexDirection: 'row', gap: 14, paddingVertical: 14, borderTopWidth: 1,
          borderTopColor: colors.border }}>
          <Text variant="scoreMetric" style={{ fontSize: 24, lineHeight: 26, width: 16 }}>{i + 1}</Text>
          <Text variant="body" style={{ flex: 1 }}>{s}</Text>
        </View>
      ))}
    </Section>
  );

  const upload = (
    <View>
      <Section title="Upload" note="export.zip or export.xml">
        {canPickFile ? (
          <DropZone onFile={start} disabled={busy}
            note="Files up to 2 GB. Re-importing the same file is safe, duplicates are skipped." />
        ) : (
          <Text color="textSecondary">Importing a file works on the computer view. On iPhone, data comes from Apple Health.</Text>
        )}
      </Section>
      {job && p ? (
        <Section title="Importing" note={`${job.name} · ${fileSize(job.bytes)}`}>
          <View style={{ marginTop: 4 }}>
            <ProgressBar share={p.share} />
          </View>
          <Text variant="labelSmall" color="textMuted" style={{ marginTop: 8, marginBottom: 4 }}>
            {Math.round(p.share * 100)}% · {p.phase}
          </Text>
          <ListRow label="Heart rate" value={`${thousands(counts.heart_rate ?? 0)} readings`} />
          <ListRow label="HRV" value={`${thousands(counts.hrv_sdnn ?? 0)} readings`} />
          <ListRow label="Sleep" value={`${thousands(counts.sleep_stages ?? 0)} pieces`} />
          <ListRow label="Nights ready" value={done ? `${job.status?.nights_ready ?? 0} nights` : 'After the import'} />
          <View style={{ borderTopWidth: 1, borderTopColor: colors.border }} />
          {job.error || job.status?.error ? (
            <Text variant="bodySmall" color="low" style={{ marginTop: 10 }}>{job.error ?? job.status?.error}</Text>
          ) : null}
          {done ? <Button title="Go to Today" style={{ alignSelf: 'flex-start', marginTop: 16 }}
            onPress={() => router.replace('/today')} /> : null}
        </Section>
      ) : null}
    </View>
  );

  return (
    <Page>
      <SubPageHeader back="Profile" label="Your data" title="Import an Apple Health export"
        intro="Bring in past nights from the Health app on your iPhone. We keep only heart rate, resting heart rate, HRV and sleep. Everything else in the file is ignored." />
      {isWide ? (
        <View style={{ flexDirection: 'row', gap: 56 }}>
          <View style={{ flex: 1 }}>{onIphone}</View>
          <View style={{ flex: 1 }}>{upload}</View>
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
