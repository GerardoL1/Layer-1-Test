/**
 * The browser version of DateTimeField: the browser's own date and time box, styled like the app's fields.
 */
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { LiveText } from '../../components/LiveText';
import { Text } from '../../components/Text';
import { dateValue } from '../../lib/logWorkout';
import { useTheme } from '../../theme/theme';
import { fonts, radius } from '../../theme/tokens';
import type { DateTimeFieldProps } from './DateTimeField';

export function DateTimeField({ id, label, mode, value, onChange, error, disabled }: DateTimeFieldProps) {
  const { colors, isDark } = useTheme();
  const [focused, setFocused] = useState(false);
  const lineColor = error ? colors.low : focused ? colors.link : 'transparent';
  return (
    <View style={styles.field}>
      <Text variant="bodySmall" color={error ? 'low' : 'textSecondary'}>{label}</Text>
      <View style={[styles.box, { backgroundColor: colors.surface, borderColor: lineColor }]}>
        <input type={mode} value={value} disabled={disabled} aria-label={label} aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
          max={mode === 'date' ? dateValue(new Date()) : undefined}
          onChange={(e) => onChange(e.currentTarget.value)}
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          // The browser's own outline is replaced by the teal one on the box, like the other fields.
          style={{ border: 0, outline: 'none', background: 'transparent', width: '100%', padding: '10px 0',
            fontFamily: fonts.sans, fontSize: 15, color: colors.textPrimary, colorScheme: isDark ? 'dark' : 'light' }} />
      </View>
      {error ? <LiveText error nativeID={`${id}-error`} variant="bodySmall" color="low">{error}</LiveText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  field: { gap: 6 },
  box: { borderWidth: 2, borderRadius: radius.sm, minHeight: 46, paddingHorizontal: 14, justifyContent: 'center' },
});
