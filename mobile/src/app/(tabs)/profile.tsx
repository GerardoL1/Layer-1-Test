import { router } from 'expo-router';
import { useState } from 'react';
import { Platform, View } from 'react-native';

import { useApi, useLoad } from '../../api/useApi';
import { Settings } from '../../api/client';
import { Chips, DaysPicker, EditRow, TextEditor, TRAINING, UPDATE_TIMES } from '../../components/Editors';
import { ListRow } from '../../components/ListRow';
import { useHealthSync } from '../../health/HealthSync';
import { Page, PageState } from '../../components/Page';
import { SectionHeader } from '../../components/SectionHeader';
import { TestBuild } from '../../components/TestBuild';
import { Text } from '../../components/Text';
import { clock, dayLabel, displayName, longDate, rangeText, WEEKDAYS } from '../../lib/format';
import { canPickFile, pickFile } from '../../lib/pickFile';
import { Appearance, useSession } from '../../state/session';
import { useTheme } from '../../theme/theme';

const APPEARANCE: { value: Appearance; label: string }[] = [
  { value: 'system', label: 'Match system' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' },
];
const USUAL_LABELS: Record<string, string> = { hrv: 'HRV', rhr: 'Resting heart rate', sleep: 'Total sleep',
  fragmentation: 'Awakenings' };

const deviceTimeZone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return 'UTC';
  }
};

export default function ProfileScreen() {
  const api = useApi();
  const session = useSession();
  const { colors, isWide } = useTheme();
  const health = useHealthSync();
  const { data: p, error, loading, reload } = useLoad(() => api.profile(), api);
  const [open, setOpen] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [importNote, setImportNote] = useState<string | null>(null);

  const toggle = (key: string) => {
    setSaveError(null);
    setOpen(open === key ? null : key);
  };
  async function save(changes: Partial<Settings>, close = true) {
    setSaveError(null);
    try {
      await api.saveSettings(changes);
      if (close) setOpen(null);
      reload();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    }
  }

  async function importExport() {
    const file = await pickFile('.zip,.xml');
    if (!file) return;
    setImportNote(`Uploading ${file.name}…`);
    try {
      await api.importExport(file, file.name);
      // The server reads the file in the background. Check every 2 s until it's done.
      for (;;) {
        await new Promise((r) => setTimeout(r, 2000));
        const s = await api.importStatus();
        if (s.state === 'done') {
          setImportNote(`Imported. ${s.counts?.new ?? 0} new readings.`);
          reload();
          return;
        }
        if (s.state === 'error') {
          setImportNote(`Import failed: ${s.error}`);
          return;
        }
        setImportNote(s.state === 'processing' ? 'Working out your nights…' : 'Reading the export…');
      }
    } catch (e) {
      setImportNote(e instanceof Error ? e.message : String(e));
    }
  }

  if (!p) return <Page><PageState loading={loading} error={error} /></Page>;
  const s = p.settings;
  const watch = p.sources.some((x) => x.includes('Apple Watch'));

  const left = (
    <View>
      <SectionHeader title="Data source" note="Apple Watch only" />
      {Platform.OS === 'ios'
        ? (
          <View>
            <ListRow label="Apple Health" value={health.syncing ? 'Syncing…' : 'Sync now'} onPress={async () => {
              await health.syncNow();
              reload();
            }} />
            {health.lastError || health.lastResult ? (
              <Text variant="bodySmall" color={health.lastError ? 'low' : 'textSecondary'} style={{ paddingBottom: 12 }}>
                {health.lastError ?? health.lastResult?.message}
              </Text>
            ) : null}
            <ListRow label="Permissions" value="Set up" onPress={() => router.push('/setup/health')} />
          </View>
        )
        : <ListRow label="Apple Health" value="iPhone app or export" />}
      <ListRow label="Watch" value={watch ? 'Apple Watch' : 'Not found yet'} />
      <ListRow label="Last update" value={p.last_update_local
        ? `${dayLabel(p.last_update_local)}, ${clock(p.last_update_local)}` : 'Not yet'} />
      <ListRow label="What we read" value="HRV, heart rate, sleep" />
      {canPickFile ? (
        <View>
          <ListRow label="Import Apple Health export" value="export.zip" onPress={importExport} />
          {importNote ? <Text variant="bodySmall" color="textSecondary" style={{ paddingBottom: 12 }}>{importNote}</Text> : null}
        </View>
      ) : null}

      <View style={{ marginTop: 32 }}>
        <SectionHeader title="Your usual" note={`Previous ${p.baseline_window_nights} nights`} />
        {p.usual_ranges.filter((u) => USUAL_LABELS[u.key]).map((u) => (
          <ListRow key={u.key} label={USUAL_LABELS[u.key]}
            value={rangeText(u.usual_low, u.usual_high, u.key) ?? `Needs ${p.baseline_min_nights} nights`} />
        ))}
        {p.usual_ranges.length === 0 ? <ListRow label="Usual ranges" value={`Need ${p.baseline_min_nights} nights`} /> : null}
      </View>
    </View>
  );

  const right = (
    <View>
      <SectionHeader title="About you" />
      <EditRow label="Age" value={s.age ? String(s.age) : 'Choose'} open={open === 'age'} onToggle={() => toggle('age')}
        error={saveError}>
        <TextEditor initial={s.age ? String(s.age) : ''} keyboard="number-pad" placeholder="Age"
          onSave={(t) => save({ age: t ? Number(t) : null })} />
      </EditRow>
      <EditRow label="Main training" value={s.training ?? 'Choose'} open={open === 'training'}
        onToggle={() => toggle('training')} error={saveError}>
        <Chips options={TRAINING.map((t) => ({ value: t, label: t }))} value={s.training}
          onPick={(t) => save({ training: t })} />
      </EditRow>
      <EditRow label="Training days" value={s.training_days.length ? s.training_days.map((d) => WEEKDAYS[d]).join(' · ') : 'Choose'}
        open={open === 'days'} onToggle={() => toggle('days')} error={saveError}>
        <DaysPicker value={s.training_days} onChange={(days) => save({ training_days: days }, false)} />
      </EditRow>

      <View style={{ marginTop: 32 }}>
        <SectionHeader title="Settings" />
        <EditRow label="Appearance" value={APPEARANCE.find((a) => a.value === session.appearance)!.label}
          open={open === 'appearance'} onToggle={() => toggle('appearance')}>
          <Chips options={APPEARANCE} value={session.appearance} onPick={(a) => session.update({ appearance: a })} />
        </EditRow>
        <EditRow label="Update time" value={clock(s.update_time)} open={open === 'update'}
          onToggle={() => toggle('update')} error={saveError}>
          <Text variant="bodySmall" color="textSecondary">
            Last night is processed once this time passes. Night-shift workers can pick a later time.
            You can always tap Update now on Today after you wake up.
          </Text>
          <Chips options={UPDATE_TIMES.map((t) => ({ value: t, label: clock(t) }))} value={s.update_time}
            onPick={(t) => save({ update_time: t })} />
        </EditRow>
        <EditRow label="Time zone" value={s.timezone ?? 'From your watch data'} open={open === 'tz'}
          onToggle={() => toggle('tz')} error={saveError}>
          <TextEditor initial={s.timezone ?? deviceTimeZone()} placeholder="America/Chicago"
            hint={`This device is in ${deviceTimeZone()}.`} onSave={(t) => save({ timezone: t || null })} />
        </EditRow>
        <ListRow label="Check-in reminder" comingSoon onPress={() => {}} />
        <EditRow label="Units" value={s.units === 'imperial' ? 'lb · ft' : 'kg · m'} open={open === 'units'}
          onToggle={() => toggle('units')} error={saveError}>
          <Chips options={[{ value: 'metric' as const, label: 'kg · m' }, { value: 'imperial' as const, label: 'lb · ft' }]}
            value={s.units} onPick={(u) => save({ units: u })} />
        </EditRow>
      </View>

      <View style={{ marginTop: 32 }}>
        <SectionHeader title="Your data" />
        <ListRow label="Export my data" comingSoon onPress={() => {}} />
        <ListRow label="Delete my data" danger comingSoon onPress={() => {}} />
      </View>
    </View>
  );

  return (
    <Page>
      <Text variant="labelSmall" color="textSecondary">Profile</Text>
      <Text variant="h1" accessibilityRole="header" style={{ marginTop: 4 }}>{displayName(p.user_id)}</Text>
      <Text variant="body" color="textSecondary" style={{ marginTop: 4, marginBottom: 24 }}>
        {p.first_night ? `Tracking since ${longDate(p.first_night)} · ${p.nights_usable} nights recorded` : 'No nights yet'}
      </Text>
      {isWide ? (
        <View style={{ flexDirection: 'row', gap: 56 }}>
          <View style={{ flex: 1 }}>{left}</View>
          <View style={{ flex: 1 }}>{right}</View>
        </View>
      ) : (
        <>
          {left}
          <View style={{ marginTop: 32 }}>{right}</View>
        </>
      )}
      <View style={{ marginTop: 24 }}>
        <ListRow label="Switch tester" onPress={async () => {
          await session.signOut();
          router.replace('/setup');
        }} />
        <TestBuild />
      </View>
      <Text variant="bodySmall" color="textMuted" style={{ marginTop: 24, paddingTop: 12, borderTopWidth: 1,
        borderTopColor: colors.border }}>
        Readiness is a training guide, not medical advice. Version 0.1 (test build).
      </Text>
    </Page>
  );
}
