/**
 * Profile > Settings > Update time: when each day last night gets processed.
 * Presets 6 to 10 am, or any other time for people who work nights.
 */
import { router } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { NumberedSteps } from '../../components/NumberedSteps';
import { SectionHeader } from '../../components/SectionHeader';
import { SubPageHeader } from '../../components/SubPageHeader';
import { LiveText } from '../../components/LiveText';
import { Text } from '../../components/Text';
import { clock, parseTime } from '../../lib/format';
import { errorText, useLoad } from '../../lib/useLoad';
import { useTheme } from '../../theme/theme';
import { radius, type } from '../../theme/tokens';
import { TimeRow } from './TimeRow';

const PRESETS = ['06:00', '07:00', '08:00', '09:00', '10:00'];

export default function UpdateTimeScreen() {
  const api = useApi();
  const { colors, isWide } = useTheme();
  const { data: settings } = useLoad(() => api.settings(), api);
  const [picked, setPicked] = useState<string | null>(null);
  const [otherOpen, setOtherOpen] = useState(false);
  const [otherText, setOtherText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const selected = picked ?? settings?.update_time ?? '08:00';
  const isPreset = PRESETS.includes(selected);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.saveSettings({ update_time: selected });
      if (router.canGoBack()) router.back();
      else router.replace('/profile');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  function applyOther() {
    const t = parseTime(otherText);
    if (!t) {
      setError('Type a time like 4:00 pm or 16:00.');
      return;
    }
    setError(null);
    setPicked(t);
    setOtherOpen(false);
  }

  const choose = (
    <View>
      {isWide ? <SectionHeader title="Choose a time" /> : null}
      {PRESETS.map((t) => (
        <TimeRow key={t} label={clock(t)} selected={selected === t} onPress={() => {
          setPicked(t);
          setOtherOpen(false);
          setError(null);
        }} />
      ))}
      <TimeRow label={isPreset ? 'Other time' : `Other time · ${clock(selected)}`} selected={!isPreset} arrow
        onPress={() => setOtherOpen(!otherOpen)}>
        {otherOpen ? (
          <View style={styles.other}>
            <TextInput value={otherText} onChangeText={setOtherText} placeholder="4:00 pm" autoFocus
              placeholderTextColor={colors.textMuted} accessibilityLabel="Other update time" onSubmitEditing={applyOther}
              style={[styles.input, { color: colors.textPrimary, borderColor: colors.border }]} />
            <Button title="Use" kind="secondary" onPress={applyOther} />
          </View>
        ) : null}
      </TimeRow>
      <View style={[styles.rule, { borderTopColor: colors.border }]} />
      <Text variant="bodySmall" color="textMuted" style={styles.hint}>
        Work nights? Pick a time after you usually wake up, for example 4:00 pm.
      </Text>
      {error ? <LiveText error variant="bodySmall" color="low" style={styles.error}>{error}</LiveText> : null}
    </View>
  );

  const howItWorks = (
    <View>
      <SectionHeader title="How it works" />
      <NumberedSteps steps={[
        `At ${clock(selected)} we process last night and update Today.`,
        'Data that arrives late is checked again the next two mornings.',
        'Up earlier? Tap Update now on Today to process last night straight away.',
      ]} />
    </View>
  );

  const header = (
    <SubPageHeader back="Profile" label="Settings" title="Daily update time"
      intro="Each day at this time we process last night and update your score. Pick a time when you are usually up and your watch has synced." />
  );

  if (isWide) {
    return (
      <ScrollView style={[styles.fill, { backgroundColor: colors.canvas }]} contentContainerStyle={styles.wideContent}>
        <View style={styles.wideColumn}>
          {header}
          <View style={styles.columns}>
            <View style={styles.fill}>
              {choose}
              <Button title="Save" busy={saving} onPress={save} style={styles.saveWide} />
            </View>
            <View style={styles.fill}>{howItWorks}</View>
          </View>
        </View>
      </ScrollView>
    );
  }
  // iPhone: Save stays at the bottom while the rest scrolls.
  return (
    <SafeAreaView edges={['bottom']} style={[styles.fill, { backgroundColor: colors.canvas }]}>
      <ScrollView style={styles.fill} contentContainerStyle={styles.phoneContent}>
        {header}
        {choose}
        <View style={styles.howItWorks}>{howItWorks}</View>
      </ScrollView>
      <View style={styles.saveBar}>
        <Button title="Save" busy={saving} onPress={save} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  other: { flexDirection: 'row', gap: 8, paddingBottom: 12 },
  input: { ...type.body, flex: 1, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10 },
  rule: { borderTopWidth: 1 },
  hint: { marginTop: 12 },
  error: { marginTop: 8 },
  wideContent: { paddingHorizontal: 48, paddingTop: 40, paddingBottom: 40 },
  wideColumn: { width: '100%', maxWidth: 1112, alignSelf: 'center' },
  columns: { flexDirection: 'row', gap: 56 },
  saveWide: { alignSelf: 'flex-start', marginTop: 20 },
  phoneContent: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 24 },
  howItWorks: { marginTop: 28 },
  saveBar: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 16 },
});
