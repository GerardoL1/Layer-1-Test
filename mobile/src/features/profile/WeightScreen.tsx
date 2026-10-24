/**
 * Profile > About you > Weight (also opened from Setup "About you").
 * Used for sweat loss as a share of body weight. Shown in kg or lb following Settings → Units.
 */
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { ListRow } from '../../components/ListRow';
import { LiveText } from '../../components/LiveText';
import { SectionHeader } from '../../components/SectionHeader';
import { SubPageHeader } from '../../components/SubPageHeader';
import { Text } from '../../components/Text';
import { errorText, useLoad } from '../../lib/useLoad';
import { parseWeight, weightInput, weightUnit } from '../../lib/weight';
import { useTheme } from '../../theme/theme';
import { type } from '../../theme/tokens';

function leave() {
  if (router.canGoBack()) router.back();
  else router.replace('/profile');
}

/** back: what the back link says, "Profile" or "About you" during setup. */
export default function WeightScreen({ back = 'Profile' }: { back?: string }) {
  const api = useApi();
  const { colors, isWide } = useTheme();
  const { data: settings } = useLoad(() => api.settings(), api);
  const units = settings?.units ?? 'metric';
  // null until the person types, so the box shows the saved weight once it has loaded.
  const [typed, setTyped] = useState<string | null>(null);
  const text = typed ?? (settings ? weightInput(settings.weight_kg, settings.units) : '');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    const parsed = parseWeight(text, units);
    if ('error' in parsed) {
      setError(parsed.error);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.saveSettings({ weight_kg: parsed.kg });
      leave();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  const other = units === 'imperial' ? 'kg' : 'lb';
  const lineColor = error ? colors.low : colors.borderStrong;
  const field = (
    <View>
      <Text variant="labelSmall" color={error ? 'low' : 'textSecondary'}>Weight</Text>
      <View style={[styles.inputRow, { borderBottomColor: lineColor }]}>
        <TextInput value={text} onChangeText={setTyped} keyboardType="decimal-pad" onSubmitEditing={save}
          accessibilityLabel={`Weight in ${weightUnit(units) === 'kg' ? 'kilograms' : 'pounds'}`}
          style={[styles.input, { color: colors.textPrimary }]} />
        <Text variant="bodySmall" color="textMuted" aria-hidden>{weightUnit(units)}</Text>
      </View>
      {error ? <LiveText error variant="bodySmall" color="low" style={styles.error}>{error}</LiveText> : null}
      <Text variant="bodySmall" color="textSecondary" style={styles.hint}>
        Units follow Settings → Units. Switch to {other} there.
      </Text>
    </View>
  );
  const cancel = (
    <Pressable accessibilityRole="button" onPress={leave} style={styles.cancel}>
      <Text variant="button" color="textSecondary">Cancel</Text>
    </Pressable>
  );
  const header = (
    <SubPageHeader back={back} label="About you" title="Weight"
      intro="Used to work out sweat loss as a share of your body weight. Only you can see it." />
  );

  if (isWide) {
    return (
      <ScrollView style={[styles.fill, { backgroundColor: colors.canvas }]} contentContainerStyle={styles.wideContent}>
        <View style={styles.wideColumn}>
          {header}
          <View style={styles.columns}>
            <View style={styles.fill}>
              {field}
              <View style={styles.wideActions}>
                <Button title="Save" busy={saving} onPress={save} />
                {cancel}
              </View>
            </View>
            <View style={styles.fill}>
              <SectionHeader title="Where it’s used" />
              <ListRow label="Sweat loss" value="% of body weight" />
              <ListRow label="Readiness score" value="Only with sweat data" />
            </View>
          </View>
        </View>
      </ScrollView>
    );
  }
  return (
    <SafeAreaView edges={['bottom']} style={[styles.fill, { backgroundColor: colors.canvas }]}>
      <ScrollView style={styles.fill} contentContainerStyle={styles.phoneContent} keyboardShouldPersistTaps="handled">
        {header}
        {field}
        <Button title="Save" busy={saving} onPress={save} style={styles.savePhone} />
        {cancel}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  inputRow: { flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, minHeight: 44, gap: 8 },
  input: { ...type.bodyLarge, flex: 1, paddingVertical: 8 },
  error: { marginTop: 8 },
  hint: { marginTop: 12 },
  cancel: { minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  savePhone: { marginTop: 28 },
  wideContent: { paddingHorizontal: 48, paddingTop: 40, paddingBottom: 40 },
  wideColumn: { width: '100%', maxWidth: 1112, alignSelf: 'center' },
  columns: { flexDirection: 'row', gap: 56 },
  wideActions: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 20 },
  phoneContent: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 24 },
});
