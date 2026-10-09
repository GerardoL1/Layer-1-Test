/**
 * Small inline editors that open under a list row (Profile and Setup "About you").
 * Kept simple on purpose: chips to pick from, and a text box where a list doesn't fit.
 */
import { useState } from 'react';
import { Pressable, TextInput, View } from 'react-native';

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
      style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.sm, borderWidth: 1,
        borderColor: on ? colors.borderStrong : colors.border, backgroundColor: on ? colors.inverse : 'transparent' }}>
      <Text variant="body" style={{ color: on ? colors.canvas : colors.textPrimary }}>{label}</Text>
    </Pressable>
  );
}

export function Chips<T extends string | number>({ options, value, onPick, label }: {
  options: { value: T; label: string }[]; value: T | null; onPick: (v: T) => void; label?: (v: T) => string;
}) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
      {options.map((o) => <Chip key={String(o.value)} label={label ? label(o.value) : o.label} on={o.value === value}
        onPress={() => onPick(o.value)} />)}
    </View>
  );
}

export function DaysPicker({ value, onChange }: { value: number[]; onChange: (days: number[]) => void }) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
      {WEEKDAYS.map((d, i) => (
        <Chip key={d} label={d} on={value.includes(i)}
          onPress={() => onChange(value.includes(i) ? value.filter((x) => x !== i) : [...value, i].sort())} />
      ))}
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
  return (
    <View style={{ gap: 8 }}>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <TextInput value={text} onChangeText={setText} placeholder={placeholder} keyboardType={keyboard}
          autoCapitalize="none" autoCorrect={false} placeholderTextColor={colors.textMuted}
          style={{ ...type.body, flex: 1, color: colors.textPrimary, borderWidth: 1, borderColor: colors.border,
            borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10 }} />
        <Button title="Save" busy={busy} onPress={async () => {
          setBusy(true);
          try {
            await onSave(text.trim());
          } finally {
            setBusy(false);
          }
        }} />
      </View>
      {hint ? <Text variant="bodySmall" color="textMuted">{hint}</Text> : null}
    </View>
  );
}

// Common morning times, plus later ones for night-shift workers.
export const UPDATE_TIMES = ['06:00', '07:00', '08:00', '09:00', '10:00', '12:00', '14:00', '17:00'];

/** A list row that opens an editor under itself when tapped. */
export function EditRow({ label, value, children, open, onToggle, error }: {
  label: string; value: string; children: React.ReactNode; open: boolean; onToggle: () => void; error?: string | null;
}) {
  return (
    <View>
      <ListRow label={label} value={value} onPress={onToggle} />
      {open ? (
        <View style={{ paddingBottom: 16, gap: 8 }}>
          {children}
          {error ? <Text variant="bodySmall" color="low">{error}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}
