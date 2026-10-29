import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useApi } from '../../api/useApi';
import { Button } from '../../components/Button';
import { LiveText } from '../../components/LiveText';
import { Notice } from '../../components/Notice';
import { deviceTimeZone } from '../../lib/timeZone';
import { errorText, useLoad } from '../../lib/useLoad';

/**
 * Shown when the saved time zone isn't the phone's, say after a flight. The daily update follows the saved one,
 * so the person can switch to the phone's or pick another in Profile. Nothing shows when none is saved.
 */
export function TimeZoneNote({ onChanged }: { onChanged: () => void }) {
  const api = useApi();
  const { data, reload } = useLoad(() => api.settings(), api);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const phone = deviceTimeZone();
  const saved = data?.timezone;
  if (!saved || saved === phone) return null;

  async function usePhone() {
    setBusy(true);
    setError(null);
    try {
      await api.saveSettings({ timezone: phone });
      reload();
      onChanged();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.note}>
      <Notice type="info" label="Time zone">
        {`Your phone is in ${phone}, but your profile says ${saved}. Your daily update follows your profile.`}
      </Notice>
      <View style={styles.buttons}>
        <Button title={`Use ${phone}`} kind="secondary" onPress={usePhone} busy={busy} />
        <Button title="Change time zone" kind="secondary" onPress={() => router.push('/profile')} />
      </View>
      {error ? <LiveText error variant="bodySmall" color="low">{error}</LiveText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  note: { gap: 12, marginTop: 20 },
  buttons: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
});
