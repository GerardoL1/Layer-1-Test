import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { Settings } from '../../api/client';
import { Chips, DaysPicker, EditRow, TextEditor, TRAINING } from '../../components/Editors';
import { ListRow } from '../../components/ListRow';
import { SectionHeader } from '../../components/SectionHeader';
import { clock, WEEKDAYS } from '../../lib/format';
import { canPickFile } from '../../lib/pickFile';
import { deviceTimeZone } from '../../lib/timeZone';
import { Appearance, useSession } from '../../state/session';
import { useSettingsEditor } from '../settings/useSettingsEditor';

const APPEARANCE: { value: Appearance; label: string }[] = [
  { value: 'system', label: 'Match system' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' },
];
const UNITS = [{ value: 'metric' as const, label: 'kg · m' }, { value: 'imperial' as const, label: 'lb · ft' }];

/** Right side of Profile: about you, settings, and your data. */
export function ProfileSettings({ settings: s, reload }: { settings: Settings; reload: () => void }) {
  const session = useSession();
  const { isOpen, toggle, save, error } = useSettingsEditor(reload);
  return (
    <View>
      <SectionHeader title="About you" />
      <EditRow label="Age" value={s.age ? String(s.age) : 'Choose'} open={isOpen('age')} onToggle={() => toggle('age')}
        error={error}>
        <TextEditor initial={s.age ? String(s.age) : ''} keyboard="number-pad" placeholder="Age"
          onSave={(t) => save({ age: t ? Number(t) : null })} />
      </EditRow>
      <EditRow label="Main training" value={s.training ?? 'Choose'} open={isOpen('training')}
        onToggle={() => toggle('training')} error={error}>
        <Chips options={TRAINING.map((t) => ({ value: t, label: t }))} value={s.training}
          onPick={(t) => save({ training: t })} />
      </EditRow>
      <EditRow label="Training days" value={s.training_days.length ? s.training_days.map((d) => WEEKDAYS[d]).join(' · ') : 'Choose'}
        open={isOpen('days')} onToggle={() => toggle('days')} error={error}>
        <DaysPicker value={s.training_days} onChange={(days) => save({ training_days: days }, false)} />
      </EditRow>

      <View style={styles.group}>
        <SectionHeader title="Settings" />
        <EditRow label="Appearance" value={APPEARANCE.find((a) => a.value === session.appearance)!.label}
          open={isOpen('appearance')} onToggle={() => toggle('appearance')}>
          <Chips options={APPEARANCE} value={session.appearance} onPick={(a) => session.update({ appearance: a })} />
        </EditRow>
        <ListRow label="Update time" value={clock(s.update_time)} onPress={() => router.push('/profile/update-time')} />
        <EditRow label="Time zone" value={s.timezone ?? 'From your watch data'} open={isOpen('tz')}
          onToggle={() => toggle('tz')} error={error}>
          <TextEditor initial={s.timezone ?? deviceTimeZone()} placeholder="America/Chicago"
            hint={`This device is in ${deviceTimeZone()}.`} onSave={(t) => save({ timezone: t || null })} />
        </EditRow>
        <ListRow label="Check-in reminder" comingSoon onPress={() => {}} />
        <EditRow label="Units" value={s.units === 'imperial' ? 'lb · ft' : 'kg · m'} open={isOpen('units')}
          onToggle={() => toggle('units')} error={error}>
          <Chips options={UNITS} value={s.units} onPick={(u) => save({ units: u })} />
        </EditRow>
      </View>

      <View style={styles.group}>
        <SectionHeader title="Your data" />
        {canPickFile ? (
          <ListRow label="Import Apple Health export" value="export.zip" onPress={() => router.push('/profile/import')} />
        ) : null}
        <ListRow label="Export my data" comingSoon onPress={() => {}} />
        <ListRow label="Delete my data" danger comingSoon onPress={() => {}} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  group: { marginTop: 32 },
});
