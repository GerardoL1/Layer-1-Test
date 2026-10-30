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
import { LiveText } from './LiveText';
import { Text } from './Text';

export const TRAINING = ['Strength', 'Endurance', 'Mixed', 'Team sport', 'Other'];

/** multi: one of several that can be on together (days), so a checkbox. Otherwise one choice of many, a radio. */
function Chip({ label, on, onPress, multi }: { label: string; on: boolean; onPress: () => void; multi?: boolean }) {
  const { colors } = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole={multi ? 'checkbox' : 'radio'} aria-checked={on}
      style={[styles.chip, { backgroundColor: on ? colors.inverse : colors.surface }]}>
      <Text variant="body" style={{ color: on ? colors.canvas : colors.textPrimary }}>{label}</Text>
    </Pressable>
  );
}

/** name: what screen readers call the group, like "Main training". */
export function Chips<T extends string | number>({ options, value, onPick, label, name }: {
  options: { value: T; label: string }[]; value: T | null; onPick: (v: T) => void; label?: (v: T) => string;
  name: string;
}) {
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={name} style={styles.chips}>
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
    <View role="group" accessibilityLabel="Training days" style={styles.chips}>
      {WEEKDAYS.map((d, i) => <Chip key={d} label={d} on={days.includes(i)} multi onPress={() => toggle(i)} />)}
    </View>
  );
}

/** label: what screen readers call the box, like "Time zone". The placeholder is only an example. */
export function TextEditor({ initial, label, placeholder, keyboard, onSave, hint }: {
  initial: string; label: string; placeholder?: string; keyboard?: 'number-pad' | 'default'; hint?: string;
  onSave: (text: string) => Promise<void>;
}) {
  const { colors } = useTheme();
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [focused, setFocused] = useState(false);
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
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          autoCapitalize="none" autoCorrect={false} placeholderTextColor={colors.textMuted}
          accessibilityLabel={label} accessibilityHint={hint} onSubmitEditing={submit} returnKeyType="done"
          style={[styles.input, { color: colors.textPrimary, backgroundColor: colors.surface,
            borderColor: focused ? colors.link : 'transparent' }]} />
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
      <ListRow label={label} value={value} onPress={onToggle} expanded={open} />
      {open ? (
        <View style={styles.opened}>
          {children}
          {error ? <LiveText error variant="bodySmall" color="low">{error}</LiveText> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  chip: { minHeight: 44, minWidth: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.full },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  editor: { gap: 8 },
  inputRow: { flexDirection: 'row', gap: 8 },
  input: { ...type.body, flex: 1, borderWidth: 2, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10,
    outlineStyle: 'solid', outlineWidth: 0 },
  opened: { paddingBottom: 16, gap: 8 },
});
