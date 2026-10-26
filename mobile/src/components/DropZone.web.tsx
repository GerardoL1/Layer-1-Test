/**
 * Dashed drop area for the Health export (computer only). Drop the file on it, or use
 * Choose file. Metro picks this file on the web, DropZone.tsx everywhere else.
 */
import { DragEvent, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { pickFile } from '../lib/pickFile';
import { useTheme } from '../theme/theme';
import { Button } from './Button';
import { Text } from './Text';

/** title and accept default to the Health export, the first thing this was used for. */
type Props = { onFile: (file: File) => void; disabled?: boolean; note?: string; title?: string; accept?: string };

export function DropZone({ onFile, disabled, note, title = 'Drop export.zip here', accept = '.zip,.xml' }: Props) {
  const { colors } = useTheme();
  const [over, setOver] = useState(false);

  // Plain DOM events: React Native's View has no drag and drop.
  const handlers = {
    onDragOver: (e: DragEvent) => {
      e.preventDefault();
      if (!disabled) setOver(true);
    },
    onDragLeave: () => setOver(false),
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      setOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file && !disabled) onFile(file);
    },
  };

  return (
    <div {...handlers} style={{ position: 'relative', padding: '28px 20px', background: over ? colors.surface : 'transparent' }}>
      {/* CSS dashes can't be sized, so the 6/4 dashed border from Figma is drawn with SVG. */}
      <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} aria-hidden>
        <rect x="0.5" y="0.5" style={{ width: 'calc(100% - 1px)', height: 'calc(100% - 1px)' }} fill="none"
          stroke={colors.borderStrong} strokeWidth="1" strokeDasharray="6 4" />
      </svg>
      <View style={styles.content}>
        <Text variant="h3">{title}</Text>
        {/* Muted text is too faint on the highlighted background while a file is dragged over. */}
        <Text variant="bodySmall" color={over ? 'textSecondary' : 'textMuted'}>or</Text>
        <Button title="Choose file" kind="secondary" disabled={disabled} style={styles.choose}
          onPress={async () => {
            const file = await pickFile(accept);
            if (file) onFile(file);
          }} />
        {note ? <Text variant="bodySmall" color={over ? 'textSecondary' : 'textMuted'} style={styles.note}>{note}</Text> : null}
      </View>
    </div>
  );
}

const styles = StyleSheet.create({
  content: { alignItems: 'center', gap: 6 },
  choose: { marginTop: 4 },
  note: { marginTop: 10, textAlign: 'center' },
});
