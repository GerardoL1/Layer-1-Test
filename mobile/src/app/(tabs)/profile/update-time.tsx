/**
 * Profile > Settings > Update time: when each day last night gets processed.
 * Presets 6 to 10 am, or any other time for people who work nights.
 */
import { router } from 'expo-router';
import { ReactNode, useState } from 'react';
import { Pressable, ScrollView, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useApi, useLoad } from '../../../api/useApi';
import { Button } from '../../../components/Button';
import { SectionHeader } from '../../../components/SectionHeader';
import { SubPageHeader } from '../../../components/SubPageHeader';
import { Text } from '../../../components/Text';
import { clock, parseTime } from '../../../lib/format';
import { useTheme } from '../../../theme/theme';
import { radius, type } from '../../../theme/tokens';

const PRESETS = ['06:00', '07:00', '08:00', '09:00', '10:00'];

function TimeRow({ label, selected, onPress, arrow, children }: {
  label: string; selected: boolean; onPress: () => void; arrow?: boolean; children?: ReactNode;
}) {
  const { colors } = useTheme();
  return (
    <View style={{ borderTopWidth: 1, borderTopColor: colors.border }}>
      <Pressable onPress={onPress} accessibilityRole="radio" accessibilityState={{ checked: selected }}
        style={{ minHeight: 51, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text variant="bodyEmphasis">{label}</Text>
        <View style={{ flexDirection: 'row', gap: 10 }}>
          {selected ? <Text variant="body" color="accent">Selected</Text> : null}
          {arrow ? <Text variant="body" color="textSecondary">→</Text> : null}
        </View>
      </Pressable>
      {children}
    </View>
  );
}

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
      setError(e instanceof Error ? e.message : String(e));
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
          <View style={{ flexDirection: 'row', gap: 8, paddingBottom: 12 }}>
            <TextInput value={otherText} onChangeText={setOtherText} placeholder="4:00 pm" autoFocus
              placeholderTextColor={colors.textMuted} accessibilityLabel="Other update time" onSubmitEditing={applyOther}
              style={{ ...type.body, flex: 1, color: colors.textPrimary, borderWidth: 1, borderColor: colors.border,
                borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10 }} />
            <Button title="Use" kind="secondary" onPress={applyOther} />
          </View>
        ) : null}
      </TimeRow>
      <View style={{ borderTopWidth: 1, borderTopColor: colors.border }} />
      <Text variant="bodySmall" color="textMuted" style={{ marginTop: 12 }}>
        Work nights? Pick a time after you usually wake up, for example 4:00 pm.
      </Text>
      {error ? <Text variant="bodySmall" color="low" style={{ marginTop: 8 }}>{error}</Text> : null}
    </View>
  );

  const steps = [
    `At ${clock(selected)} we process last night and update Today.`,
    'Data that arrives late is checked again the next two mornings.',
    'Up earlier? Tap Update now on Today to process last night straight away.',
  ];
  const howItWorks = (
    <View>
      <SectionHeader title="How it works" />
      {steps.map((s, i) => (
        <View key={i} style={{ flexDirection: 'row', gap: 14, paddingVertical: 14, borderTopWidth: 1,
          borderTopColor: colors.border }}>
          <Text variant="scoreMetric" style={{ fontSize: 24, lineHeight: 26, width: 16 }}>{i + 1}</Text>
          <Text variant="body" style={{ flex: 1 }}>{s}</Text>
        </View>
      ))}
    </View>
  );

  const header = (
    <SubPageHeader back="Profile" label="Settings" title="Daily update time"
      intro="Each day at this time we process last night and update your score. Pick a time when you are usually up and your watch has synced." />
  );

  if (isWide) {
    return (
      <ScrollView style={{ flex: 1, backgroundColor: colors.canvas }}
        contentContainerStyle={{ paddingHorizontal: 48, paddingTop: 40, paddingBottom: 40 }}>
        <View style={{ width: '100%', maxWidth: 1112, alignSelf: 'center' }}>
          {header}
          <View style={{ flexDirection: 'row', gap: 56 }}>
            <View style={{ flex: 1 }}>
              {choose}
              <Button title="Save" busy={saving} onPress={save} style={{ alignSelf: 'flex-start', marginTop: 20 }} />
            </View>
            <View style={{ flex: 1 }}>{howItWorks}</View>
          </View>
        </View>
      </ScrollView>
    );
  }
  // iPhone: Save stays at the bottom while the rest scrolls.
  return (
    <SafeAreaView edges={['bottom']} style={{ flex: 1, backgroundColor: colors.canvas }}>
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 16, paddingBottom: 24 }}>
        {header}
        {choose}
        <View style={{ marginTop: 28 }}>{howItWorks}</View>
      </ScrollView>
      <View style={{ paddingHorizontal: 20, paddingTop: 12, paddingBottom: 16 }}>
        <Button title="Save" busy={saving} onPress={save} />
      </View>
    </SafeAreaView>
  );
}
