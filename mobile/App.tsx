/**
 * Recovery platform — iPhone test app.
 *
 * Watch → Health app → (this app) → server → computer
 *
 * 1. "Connect Apple Health" asks for permission.
 * 2. "Send to platform" reads the last 24 hours and POSTs it to the server.
 */
import { useState } from 'react';
import { Button, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import {
  isHealthDataAvailable,
  queryQuantitySamples,
  requestAuthorization,
} from '@kingstinct/react-native-healthkit';

// HealthKit type → our metric name
const METRICS = [
  { id: 'HKQuantityTypeIdentifierHeartRate', metric: 'heart_rate' },
  { id: 'HKQuantityTypeIdentifierRestingHeartRate', metric: 'resting_heart_rate' },
  { id: 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN', metric: 'hrv_sdnn' },
] as const;

export default function App() {
  // Replace with your computer's local IP address (same Wi-Fi as the phone).
  const [serverUrl, setServerUrl] = useState('http://192.168.1.50:8000');
  const [userId, setUserId] = useState('tester1');
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const say = (line: string) =>
    setLog((prev) => [`${new Date().toLocaleTimeString()}  ${line}`, ...prev]);

  async function connectHealth() {
    if (!isHealthDataAvailable()) {
      say('Health data is not available on this device. Use a real iPhone.');
      return;
    }
    try {
      await requestAuthorization({ toRead: METRICS.map((m) => m.id) });
      say('Permission screen finished. If data is missing later, check Settings → Health → Data Access.');
    } catch (e) {
      say(`Permission error: ${String(e)}`);
    }
  }

  async function sendToPlatform() {
    setBusy(true);
    try {
      const endDate = new Date();
      const startDate = new Date(endDate.getTime() - 24 * 60 * 60 * 1000);
      const samples = [];

      for (const m of METRICS) {
        const rows = await queryQuantitySamples(m.id, {
          limit: 0, // 0 = no limit
          filter: { date: { startDate, endDate } },
        });
        say(`Read ${rows.length} ${m.metric} samples from Health`);
        for (const r of rows) {
          samples.push({
            uuid: r.uuid,
            metric: m.metric,
            value: r.quantity,
            unit: r.unit, // Health's default unit: count/min for heart rate, ms for HRV
            start_ms: new Date(r.startDate).getTime(),
            end_ms: new Date(r.endDate).getTime(),
            source: r.sourceRevision?.source?.name ?? null,
          });
        }
      }

      if (samples.length === 0) {
        say('Nothing to send. Wear the watch for a while, or check permissions.');
        return;
      }

      const res = await fetch(`${serverUrl}/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, samples }),
      });
      if (!res.ok) throw new Error(`Server replied ${res.status}`);
      const body = await res.json();
      say(`Sent ${body.received} samples, ${body.new} were new on the server.`);
    } catch (e) {
      say(`Send failed: ${String(e)}. Is the server running and is the address right?`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <Text style={styles.title}>Recovery test</Text>

      <Text style={styles.label}>Server address</Text>
      <TextInput style={styles.input} value={serverUrl} onChangeText={setServerUrl}
        autoCapitalize="none" autoCorrect={false} keyboardType="url" />

      <Text style={styles.label}>Tester name</Text>
      <TextInput style={styles.input} value={userId} onChangeText={setUserId}
        autoCapitalize="none" autoCorrect={false} />

      <View style={styles.buttons}>
        <Button title="Connect Apple Health" onPress={connectHealth} />
        <Button title={busy ? 'Sending…' : 'Send to platform'} onPress={sendToPlatform} disabled={busy} />
      </View>

      <ScrollView style={styles.log}>
        {log.length === 0 && <Text style={styles.hint}>Tap "Connect Apple Health" first.</Text>}
        {log.map((line, i) => <Text key={i} style={styles.logLine}>{line}</Text>)}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 20, backgroundColor: '#f7f8fa' },
  title: { fontSize: 24, fontWeight: '600', marginVertical: 12, color: '#1d2433' },
  label: { fontSize: 13, color: '#5b6475', marginTop: 10 },
  input: { borderWidth: 1, borderColor: '#d9dde5', borderRadius: 6, padding: 10, backgroundColor: '#fff', marginTop: 4 },
  buttons: { marginVertical: 16, gap: 8 },
  log: { flex: 1, backgroundColor: '#fff', borderRadius: 6, borderWidth: 1, borderColor: '#d9dde5', padding: 10 },
  hint: { color: '#5b6475' },
  logLine: { fontSize: 12, fontFamily: 'Courier', marginBottom: 6, color: '#1d2433' },
});
