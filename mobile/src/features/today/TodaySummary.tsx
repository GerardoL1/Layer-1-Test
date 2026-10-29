import { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { Today } from '../../api/client';
import { Button } from '../../components/Button';
import { LiveText } from '../../components/LiveText';
import { ReadinessBand, STATUS_WORD } from '../../components/Readiness';
import { Text } from '../../components/Text';
import { clock, fullDay, partOfDay, weekdayName } from '../../lib/format';
import { useTheme } from '../../theme/theme';

type Props = {
  today: Today & { readiness: NonNullable<Today['readiness']> };
  /** True before the update time, while Today still shows an earlier night. */
  waiting: boolean;
  /** The night before's score and the usual range, for the band. */
  previous: number | null;
  usual: [number, number] | null;
  updating: boolean;
  updateNote: string | null;
  onUpdateNow: () => void;
  /** A notice that goes between the words and the band, like the time zone note. */
  notice?: ReactNode;
};

/** "Readiness 28 of 100, which is low. <reason>", or what Today shows while last night isn't in yet. */
function lead(t: Props['today'], waiting: boolean): string | null {
  const { score, status } = t.readiness;
  const word = status in { low: 1, moderate: 1, ready: 1 } ? STATUS_WORD[status].toLowerCase() : null;
  if (waiting) {
    const night = `${weekdayName(t.night_date!)} night`;
    return `Your watch usually sends last night by ${clock(t.update_time)}. Until then, this is ${night}`
      + (score !== null && word ? `: readiness ${score}, which is ${word}.` : '.');
  }
  const head = score !== null && word ? `Readiness ${score} of 100, which is ${word}.` : null;
  return [head, t.reason].filter(Boolean).join(' ') || null;
}

/**
 * The top of Today: the date, a greeting with the verdict, why, the readiness band and the actions.
 * Before the update time it says which night is shown and offers Update now.
 */
export function TodaySummary({ today: t, waiting, previous, usual, updating, updateNote, onUpdateNow, notice }: Props) {
  const { isWide } = useTheme();
  // No name yet, so the greeting is just the time of day. A name comes with Round 6.
  const second = waiting ? 'Last night isn’t in yet.' : t.verdict;
  const greeting = `${partOfDay(t.now_local)}.${second ? (isWide ? ' ' : '\n') + second : ''}`;
  const text = lead(t, waiting);
  const date = `${fullDay(t.now_local)}${isWide && t.updated_at ? ` · updated ${clock(t.updated_at)}` : ''}`;
  const score = t.readiness.score;
  const band = score !== null ? (
    <View style={styles.band}>
      <ReadinessBand score={score} from={previous} usual={usual}
        name={waiting ? weekdayName(t.night_date!) : 'Today'} />
    </View>
  ) : null;
  // Figma: on a computer the buttons and date sit right under the words, above the note and the band.
  const actions = (
    <>
      <View style={[styles.actions, isWide && styles.actionsWide]}>
        {waiting ? (
          <Button title="Update now" kind="secondary" busy={updating} disabled={!t.can_update_now} onPress={onUpdateNow} />
        ) : null}
        {/* Check-ins come later. The button is there so the layout matches, but it does nothing yet. */}
        <Button title="Start morning check-in" disabled />
        {isWide ? <Text variant="bodySmall" color="textSecondary">{date}</Text> : null}
      </View>
      <Text variant="bodySmall" color="textMuted" style={styles.soon}>Check-ins are coming soon.</Text>
    </>
  );
  return (
    <View>
      {!isWide ? <Text variant="bodySmall" color="textSecondary">{date}</Text> : null}
      <Text variant={isWide ? 'greetingLarge' : 'greeting'} accessibilityRole="header" style={styles.greeting}>{greeting}</Text>
      {text ? <Text variant="bodyLarge" color="textSecondary" style={styles.lead}>{text}</Text> : null}
      {isWide ? actions : <>{notice}{band}</>}
      {isWide ? <>{notice}{band}</> : actions}
      {updateNote ? <LiveText variant="bodySmall" color="textSecondary" style={styles.soon}>{updateNote}</LiveText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  greeting: { marginTop: 8 },
  lead: { marginTop: 12 },
  band: { marginTop: 24 },
  actions: { marginTop: 24, gap: 12 },
  actionsWide: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' },
  soon: { marginTop: 8 },
});
