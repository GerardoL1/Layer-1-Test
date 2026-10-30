/**
 * A date or time box that opens the phone's own picker, so it works like every other iPhone app.
 * The web version is DateTimeField.web.tsx. Values are "2026-10-01" and "18:10", like lib/logWorkout.ts.
 */
import DateTimePicker, { DateTimePickerEvent } from '@react-native-community/datetimepicker';
import { useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { LiveText } from '../../components/LiveText';
import { Text } from '../../components/Text';
import { dateText, dateValue, localMoment, timeText, timeValue } from '../../lib/logWorkout';
import { useTheme } from '../../theme/theme';
import { radius } from '../../theme/tokens';

export type DateTimeFieldProps = {
  id: string; label: string; mode: 'date' | 'time'; value: string; onChange: (v: string) => void;
  placeholder?: string; error?: string | null; disabled?: boolean;
};

export function DateTimeField({ id, label, mode, value, onChange, placeholder, error, disabled }: DateTimeFieldProps) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const shown = value ? (mode === 'date' ? dateText(value) : timeText(value)) : null;
  const now = new Date();
  const current = !value ? now : mode === 'date' ? localMoment(value, '12:00') : localMoment(dateValue(now), value);
  const lineColor = error ? colors.low : open ? colors.link : 'transparent';
  return (
    <View style={styles.field}>
      <Text variant="bodySmall" color={error ? 'low' : 'textSecondary'}>{label}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel={`${label}, ${shown ?? 'not set'}`}
        accessibilityHint="Opens a picker" aria-expanded={open} disabled={disabled} onPress={() => setOpen((o) => !o)}
        style={[styles.box, { backgroundColor: colors.surface, borderColor: lineColor }]}>
        <Text variant="body" color={shown ? 'textPrimary' : 'textMuted'}>{shown ?? placeholder}</Text>
      </Pressable>
      {open ? (
        // iOS shows the wheels under the box until it's tapped again. Android shows its own dialog once.
        <DateTimePicker value={current} mode={mode} display={Platform.OS === 'ios' ? 'spinner' : 'default'}
          maximumDate={mode === 'date' ? now : undefined}
          onChange={(e: DateTimePickerEvent, d?: Date) => {
            if (Platform.OS !== 'ios') setOpen(false);
            if (e.type === 'set' && d) onChange(mode === 'date' ? dateValue(d) : timeValue(d));
          }} />
      ) : null}
      {error ? <LiveText error nativeID={`${id}-error`} variant="bodySmall" color="low">{error}</LiveText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  field: { gap: 6 },
  box: { borderWidth: 2, borderRadius: radius.sm, minHeight: 46, paddingHorizontal: 14, justifyContent: 'center' },
});
