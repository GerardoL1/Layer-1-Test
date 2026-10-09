import { router } from 'expo-router';
import { useState } from 'react';

import { Settings } from '../../api/client';
import { useApi, useLoad } from '../../api/useApi';
import { Button } from '../../components/Button';
import { Chips, DaysPicker, EditRow, TextEditor, TRAINING } from '../../components/Editors';
import { SetupFrame } from '../../components/SetupFrame';
import { Text } from '../../components/Text';
import { WEEKDAYS } from '../../lib/format';

/** Setup 3: a little about you. Everything can be skipped and changed later in Profile. */
export default function AboutStep() {
  const api = useApi();
  const { data: s, reload } = useLoad(() => api.settings().catch(() => null), api);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(changes: Partial<Settings>, close = true) {
    setError(null);
    try {
      await api.saveSettings(changes);
      if (close) setOpen(null);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  const toggle = (k: string) => setOpen(open === k ? null : k);

  return (
    <SetupFrame step={2} actions={
      <>
        <Button title="Continue" onPress={() => router.push('/setup/baseline')} />
        <Button title="Skip for now" kind="secondary" onPress={() => router.push('/setup/baseline')} />
      </>
    }>
      <Text variant="h1" accessibilityRole="header">A little about you</Text>
      <Text variant="bodyLarge" color="textSecondary" style={{ marginTop: 12, marginBottom: 20 }}>
        This helps explain your scores. It doesn&apos;t change the numbers from your watch.
      </Text>
      <EditRow label="Age" value={s?.age ? String(s.age) : 'Choose'} open={open === 'age'} onToggle={() => toggle('age')}
        error={error}>
        <TextEditor initial={s?.age ? String(s.age) : ''} keyboard="number-pad" placeholder="Age"
          onSave={(t) => save({ age: t ? Number(t) : null })} />
      </EditRow>
      <EditRow label="Main training" value={s?.training ?? 'Choose'} open={open === 'training'}
        onToggle={() => toggle('training')} error={error}>
        <Chips options={TRAINING.map((t) => ({ value: t, label: t }))} value={s?.training ?? null}
          onPick={(t) => save({ training: t })} />
      </EditRow>
      <EditRow label="Training days"
        value={s?.training_days.length ? s.training_days.map((d) => WEEKDAYS[d]).join(' · ') : 'Choose'}
        open={open === 'days'} onToggle={() => toggle('days')} error={error}>
        <DaysPicker value={s?.training_days ?? []} onChange={(days) => save({ training_days: days }, false)} />
      </EditRow>
    </SetupFrame>
  );
}
