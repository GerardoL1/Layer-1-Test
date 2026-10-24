import { router } from 'expo-router';
import { StyleSheet } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { ListRow } from '../../components/ListRow';
import { Chips, DaysPicker, EditRow, TextEditor, TRAINING } from '../../components/Editors';
import { SetupFrame } from '../../components/SetupFrame';
import { Text } from '../../components/Text';
import { WEEKDAYS } from '../../lib/format';
import { useLoad } from '../../lib/useLoad';
import { weightText } from '../../lib/weight';
import { useSettingsEditor } from '../settings/useSettingsEditor';

const AGE_HINT = 'Type your age as a whole number, like 21.';

/** Setup 3: a little about you. Everything can be skipped and changed later in Profile. */
export default function AboutStep() {
  const api = useApi();
  const { data: s, reload } = useLoad(() => api.settings().catch(() => null), api);
  const { isOpen, toggle, save, invalid, error } = useSettingsEditor(reload);

  return (
    <SetupFrame step={2} actions={
      <>
        <Button title="Continue" onPress={() => router.push('/setup/baseline')} />
        <Button title="Skip for now" kind="secondary" onPress={() => router.push('/setup/baseline')} />
      </>
    }>
      <Text variant="h1" accessibilityRole="header">A little about you</Text>
      <Text variant="bodyLarge" color="textSecondary" style={styles.intro}>
        This helps explain your scores. It doesn&apos;t change the numbers from your watch.
      </Text>
      <EditRow label="Age" value={s?.age ? String(s.age) : 'Choose'} open={isOpen('age')} onToggle={() => toggle('age')}
        error={error}>
        <TextEditor initial={s?.age ? String(s.age) : ''} label="Age" keyboard="number-pad" placeholder="Age"
          onSave={(t) => (t && !/^\d+$/.test(t) ? invalid(AGE_HINT) : save({ age: t ? Number(t) : null }))} />
      </EditRow>
      <ListRow label="Weight" value={weightText(s?.weight_kg, s?.units ?? 'metric')} onPress={() => router.push('/setup/weight')} />
      <EditRow label="Main training" value={s?.training ?? 'Choose'} open={isOpen('training')}
        onToggle={() => toggle('training')} error={error}>
        <Chips name="Main training" options={TRAINING.map((t) => ({ value: t, label: t }))} value={s?.training ?? null}
          onPick={(t) => save({ training: t })} />
      </EditRow>
      <EditRow label="Training days"
        value={s?.training_days.length ? s.training_days.map((d) => WEEKDAYS[d]).join(' · ') : 'Choose'}
        open={isOpen('days')} onToggle={() => toggle('days')} error={error}>
        <DaysPicker value={s?.training_days ?? []} onChange={(days) => save({ training_days: days }, false)} />
      </EditRow>
    </SetupFrame>
  );
}

const styles = StyleSheet.create({
  intro: { marginTop: 12, marginBottom: 20 },
});
