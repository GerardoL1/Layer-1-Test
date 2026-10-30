import { Pressable, StyleSheet, View } from 'react-native';

import { MUSCLES, type MuscleGroup } from '../lib/checkin';
import { useTheme } from '../theme/theme';
import { radius } from '../theme/tokens';
import { Panel } from './Panel';
import { Text } from './Text';

// x, y, width, height and corner radius of each shape, from the Figma "Body map" (each figure is 140 x 296).
type Shape = [number, number, number, number, number];
type Group = { m: MuscleGroup; shapes: Shape[] };

const SHOULDERS: Group = { m: 'shoulders', shapes: [[26, 50, 28, 24, 12], [86, 50, 28, 24, 12]] };
const FOREARMS: Group = { m: 'forearms', shapes: [[16, 122, 15, 44, 7.5], [109, 122, 15, 44, 7.5]] };
const ARMS: Shape[] = [[22, 78, 17, 40, 8.5], [101, 78, 17, 40, 8.5]];
const LOWER_LEGS: Shape[] = [[48, 226, 17, 54, 8.5], [75, 226, 17, 54, 8.5]];

const FRONT: Group[] = [
  SHOULDERS,
  { m: 'chest', shapes: [[46, 52, 23, 30, 7], [71, 52, 23, 30, 7]] },
  { m: 'biceps', shapes: ARMS },
  FOREARMS,
  { m: 'abs', shapes: [[53, 86, 34, 54, 7]] },
  { m: 'quads', shapes: [[45, 148, 23, 72, 11.5], [72, 148, 23, 72, 11.5]] },
  { m: 'shins', shapes: LOWER_LEGS },
];
const BACK: Group[] = [
  { m: 'traps', shapes: [[51, 44, 38, 18, 7]] },
  SHOULDERS,
  { m: 'lats', shapes: [[44, 66, 23, 46, 8], [73, 66, 23, 46, 8]] },
  { m: 'triceps', shapes: ARMS },
  FOREARMS,
  { m: 'lower_back', shapes: [[56, 116, 28, 22, 7]] },
  { m: 'glutes', shapes: [[45, 142, 23, 30, 11], [72, 142, 23, 30, 11]] },
  { m: 'hamstrings', shapes: [[45, 176, 23, 46, 11.5], [72, 176, 23, 46, 11.5]] },
  { m: 'calves', shapes: LOWER_LEGS },
];
// Outline only: head and hands.
const OUTLINE: Shape[] = [[56, 4, 28, 34, 17], [13, 169, 16, 18, 9], [111, 169, 16, 18, 9]];

const LABEL = Object.fromEntries(MUSCLES.map((g) => [g.value, g.label])) as Record<MuscleGroup, string>;

/**
 * shared: groups already drawn on the front figure (shoulders, forearms). The back copy is hidden
 * from screen readers so each muscle is read once.
 */
function Figure({ name, groups, sore, onToggle, disabled, shared }: {
  name: string; groups: Group[]; sore: MuscleGroup[]; onToggle: (m: MuscleGroup) => void; disabled?: boolean;
  shared?: MuscleGroup[];
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.side}>
      <View style={styles.figure}>
        {OUTLINE.map(([x, y, w, h, r], i) => (
          <View key={i} aria-hidden style={[styles.shape, { left: x, top: y, width: w, height: h, borderRadius: r,
            borderWidth: 1, borderColor: colors.borderStrong }]} />
        ))}
        {groups.flatMap((g) => g.shapes.map(([x, y, w, h, r], i) => {
          const on = sore.includes(g.m);
          // The first shape of a group speaks for it, the second one is only another place to tap.
          const spoken = i === 0 && !shared?.includes(g.m);
          return (
            <Pressable key={`${g.m}-${i}`} onPress={() => onToggle(g.m)} disabled={disabled}
              accessibilityRole="checkbox" aria-checked={on} accessibilityLabel={LABEL[g.m]}
              aria-hidden={!spoken} importantForAccessibility={spoken ? 'yes' : 'no-hide-descendants'}
              accessibilityElementsHidden={!spoken} tabIndex={spoken ? 0 : -1}
              style={[styles.shape, { left: x, top: y, width: w, height: h, borderRadius: r,
                backgroundColor: on ? colors.inverse : colors.surface }]} />
          );
        }))}
      </View>
      <Text variant="bodySmall" color="textSecondary" aria-hidden>{name}</Text>
    </View>
  );
}

/** Front and back figures to tap sore muscles on, and the list of what's picked (tap a row to take it off). */
export function BodyMap({ sore, onToggle, disabled }: {
  sore: MuscleGroup[]; onToggle: (m: MuscleGroup) => void; disabled?: boolean;
}) {
  const { colors, isWide } = useTheme();
  const verb = isWide ? 'click' : 'tap';
  return (
    <View style={styles.wrap}>
      <View role="group" accessibilityLabel="Sore muscles" style={styles.figures}>
        <Figure name="Front" groups={FRONT} sore={sore} onToggle={onToggle} disabled={disabled} />
        <Figure name="Back" groups={BACK} sore={sore} onToggle={onToggle} disabled={disabled}
          shared={['shoulders', 'forearms']} />
      </View>
      {sore.length ? (
        <Panel>
          {sore.map((m) => (
            <Pressable key={m} onPress={() => onToggle(m)} disabled={disabled} accessibilityRole="button"
              accessibilityLabel={`${LABEL[m]}, sore. Remove`}
              style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.surfaceMuted }]}>
              <Text variant="bodyEmphasis">{LABEL[m]}</Text>
              <Text variant="body" color="textSecondary">Sore · {verb} to remove</Text>
            </Pressable>
          ))}
        </Panel>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12 },
  figures: { flexDirection: 'row', justifyContent: 'center', gap: 48, paddingVertical: 10 },
  side: { alignItems: 'center', gap: 10 },
  figure: { width: 140, height: 296 },
  shape: { position: 'absolute' },
  row: { minHeight: 50, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12,
    borderRadius: radius.md },
});
