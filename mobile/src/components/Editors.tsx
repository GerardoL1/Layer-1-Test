/**
 * Small inline editors that open under a list row (Profile and Setup "About you").
 * Kept simple on purpose: chips to pick from, and a text box where a list doesn't fit.
 */
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { WEEKDAYS } from '../lib/format';
import { useTheme } from '../theme/theme';
import { radius, type } from '../theme/tokens';
import { Button } from './Button';
import { ListRow } from './ListRow';
import { Text } from './Text';

export const TRAINING = ['Strength', 'Endurance', 'Mixed', 'Team sport', 'Other'];

function Chip({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: on }}
      style={[styles.chip, { borderColor: on ? colors.borderStrong : colors.border,
        backgroundColor: on ? colors.inverse : 'transparent' }]}>
      <Text variant="body" style={{ color: on ? colors.canvas : colors.textPrimary }}>{label}</Text>
    </Pressable>
  );
}

export function Chips<T extends string | number>({ options, value, onPick, label }: {
  options: { value: T; label: string }[]; value: T | null; onPick: (v: T) => void; label?: (v: T) => string;
}) {
  return (
    <View style={styles.chips}>
      {options.map((o) => <Chip key={String(o.value)} label={label ? label(o.value) : o.label} on={o.value === value}
        onPress={() => onPick(o.value)} />)}
    </View>
  );
}

const DAYS_SAVE_DELAY_MS = 600;

export function DaysPicker({ value, onChange }: { value: number[]; onChange: (days: number[]) => void }) {
  // Quick taps each build on the one before (kept in a ref, so even taps closer together than a
  // render count), and one save goes out once the taps stop. One save can't arrive out of order.
  const [days, setDays] = useState(value);
  const latest = useRef(value);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const save = useRef(onChange);
  useEffect(() => {
    save.current = onChange;
  });
  // Closing the row before the delay is up still saves.
  useEffect(() => () => {
    if (timer.current) {
      clearTimeout(timer.current);
      save.current(latest.current);
    }
  }, []);

  function toggle(i: number) {
    const cur = latest.current;
    const next = cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i].sort();
    latest.current = next;
    setDays(next);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      save.current(latest.current);
    }, DAYS_SAVE_DELAY_MS);
  }
  return (
    <View style={styles.chips}>
      {WEEKDAYS.map((d, i) => <Chip key={d} label={d} on={days.includes(i)} onPress={() => toggle(i)} />)}
    </View>
  );
}

export function TextEditor({ initial, placeholder, keyboard, onSave, hint }: {
  initial: string; placeholder?: string; keyboard?: 'number-pad' | 'default'; hint?: string;
  onSave: (text: string) => Promise<void>;
}) {
  const { colors } = useTheme();
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    try {
      await onSave(text.trim());
    } finally {
      setBusy(false);
    }
  }
  return (
    <View style={styles.editor}>
      <View style={styles.inputRow}>
        <TextInput value={text} onChangeText={setText} placeholder={placeholder} keyboardType={keyboard}
          autoCapitalize="none" autoCorrect={false} placeholderTextColor={colors.textMuted}
          accessibilityLabel={placeholder} onSubmitEditing={submit} returnKeyType="done"
          style={[styles.input, { color: colors.textPrimary, borderColor: colors.border }]} />
        <Button title="Save" busy={busy} onPress={submit} />
      </View>
      {hint ? <Text variant="bodySmall" color="textMuted">{hint}</Text> : null}
    </View>
  );
}

/** A list row that opens an editor under itself when tapped. */
export function EditRow({ label, value, children, open, onToggle, error }: {
  label: string; value: string; children: React.ReactNode; open: boolean; onToggle: () => void; error?: string | null;
}) {
  return (
    <View>
      <ListRow label={label} value={value} onPress={onToggle} />
      {open ? (
        <View style={styles.opened}>
          {children}
          {error ? <Text variant="bodySmall" color="low">{error}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.sm, borderWidth: 1 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  editor: { gap: 8 },
  inputRow: { flexDirection: 'row', gap: 8 },
  input: { ...type.body, flex: 1, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10 },
  opened: { paddingBottom: 16, gap: 8 },
});
