import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Chips } from '../../components/Editors';
import { LiveText } from '../../components/LiveText';
import { Page, PageState } from '../../components/Page';
import { STATUS_WORD } from '../../components/Readiness';
import { SectionHeader } from '../../components/SectionHeader';
import { SubPageHeader } from '../../components/SubPageHeader';
import { Text } from '../../components/Text';
import { dayLabel } from '../../lib/format';
import { errorText, useLoad } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';
import { radius } from '../../theme/tokens';
import { WhatMoved } from './WhatMoved';

const ANSWERS = [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }] as const;

/**
 * Why this score: the explanation, what moved the score, how it works, and "Was this helpful?".
 * This is Figma's placeholder version: the text comes from a template, so it isn't labelled as written by AI.
 */
export default function WhyScreen() {
  const api = useApi();
  const { colors, isWide } = useTheme();
  const today = useLoad(() => api.today(), api);
  // The answer tapped here, until Today is loaded again. undefined means the saved one stands.
  const [picked, setPicked] = useState<boolean | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const t = today.data;
  const header = <SubPageHeader back="Today" home="/today" label="Readiness" title={t?.readiness?.score != null
    ? `Why your score is ${STATUS_WORD[t.readiness.status].toLowerCase()}` : 'Why this score'}
    detail={t?.readiness?.score != null && t.night_date
      ? `${dayLabel(t.night_date)} · readiness ${t.readiness.score} · ${STATUS_WORD[t.readiness.status].toLowerCase()}`
      : undefined} />;

  if (!t) return <Page>{header}<PageState loading={today.loading} error={today.error} onRetry={today.reload} /></Page>;
  if (!t.readiness || t.readiness.score === null || !t.night_date) {
    return (
      <Page>
        {header}
        <Text variant="body" color="textSecondary">There&apos;s no score to explain yet.</Text>
      </Page>
    );
  }

  const night = t.night_date;
  const helpful = picked !== undefined ? picked : t.helpful ?? null;
  async function answer(value: 'yes' | 'no') {
    const before = helpful;
    setPicked(value === 'yes');
    setError(null);
    try {
      await api.saveFeedback(night, value === 'yes');
    } catch (e) {
      // Put the earlier answer back, so the chips never show one that wasn't saved.
      setPicked(before);
      setError(errorText(e));
    }
  }

  return (
    <Page>
      {header}
      {t.reason ? <Text variant="bodyLarge">{t.reason}</Text> : null}
      <Text variant="bodySmall" color="textSecondary" style={styles.source}>
        {`Written from the numbers ${isWide ? 'on this page' : 'below'}. It can be wrong, and it isn’t medical advice.`}
      </Text>
      <View style={styles.space24}><WhatMoved today={t} /></View>
      <View style={[styles.panel, styles.space12, { backgroundColor: colors.surface }]}>
        <SectionHeader title="How the score works" />
        <Text variant="body" color="textSecondary">
          The score compares last night with your own usual from the previous 28 nights. Each measure moves it up or
          down by how far it was from your usual. The formula is a placeholder while the team builds the model.
        </Text>
      </View>
      <View style={[styles.panel, styles.space12, { backgroundColor: colors.surface }]}>
        <SectionHeader title="Was this helpful?" />
        <Chips name="Was this helpful?" options={[...ANSWERS]} onPick={answer}
          value={helpful === null ? null : helpful ? 'yes' : 'no'} />
        <LiveText variant="bodySmall" color="textSecondary" style={styles.caption}>
          {helpful === null ? 'Your answer helps the team improve these explanations.' : 'Thanks, your answer was saved.'}
        </LiveText>
        {error ? <LiveText error variant="bodySmall" color="low" style={styles.caption}>{error}</LiveText> : null}
      </View>
    </Page>
  );
}

const styles = StyleSheet.create({
  source: { marginTop: 12 },
  panel: { borderRadius: radius.lg, paddingHorizontal: 16, paddingBottom: 16 },
  space24: { marginTop: 24 },
  space12: { marginTop: 12 },
  caption: { marginTop: 12 },
});
