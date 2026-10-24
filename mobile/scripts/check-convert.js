/**
 * Checks src/health/convert.ts (HealthKit sample -> server upload) and src/lib/weight.ts (kg and lb)
 * without an iPhone.
 * Uses the TypeScript compiler the app already has, so no test framework is needed.
 *
 *   npm test
 */
const assert = require('assert');
const fs = require('fs');
const Module = require('module');
const path = require('path');
const ts = require('typescript');

function load(...parts) {
  const file = path.join(__dirname, '..', 'src', ...parts);
  const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const m = new Module(file);
  m._compile(js, file);
  return m.exports;
}
const c = load('health', 'convert.ts');
const w = load('lib', 'weight.ts');

const checks = {
  'UTC offset in a named time zone': () => {
    assert.strictEqual(c.offsetInZone('America/Chicago', Date.UTC(2026, 6, 1, 12)), -300);  // summer
    assert.strictEqual(c.offsetInZone('America/Chicago', Date.UTC(2026, 0, 1, 12)), -360);  // winter
    assert.strictEqual(c.offsetInZone('Asia/Tokyo', Date.UTC(2026, 6, 1, 12)), 540);
    assert.strictEqual(c.offsetInZone('Asia/Kolkata', Date.UTC(2026, 6, 1, 12, 0, 30, 500)), 330);
  },
  'unknown time zone gives null so the caller can fall back': () => {
    assert.strictEqual(c.offsetInZone('Not/AZone', Date.now()), null);
  },
  'a night across the clock change keeps two offsets': () => {
    const night = { uuid: 'a', value: 3, startDate: new Date(Date.UTC(2026, 10, 1, 5)),
      endDate: new Date(Date.UTC(2026, 10, 1, 12)), metadata: { HKTimeZone: 'America/Chicago' },
      sourceRevision: { source: { name: 'Sam’s Apple Watch' } } };
    const s = c.toUploadStage(night);
    assert.deepStrictEqual([s.stage, s.start_tz_min, s.end_tz_min, s.source], ['core', -300, -360, 'Sam’s Apple Watch']);
  },
  'unknown sleep values are skipped': () => {
    assert.strictEqual(c.toUploadStage({ uuid: 'x', value: 99, startDate: new Date(), endDate: new Date() }), null);
  },
  'without HKTimeZone the phone offset at that moment is used': () => {
    const when = '2026-07-01T03:00:00Z';
    const s = c.toUploadSample('heart_rate', { uuid: 'b', quantity: 52, startDate: when, endDate: when });
    assert.strictEqual(s.tz_offset_min, -new Date(when).getTimezoneOffset());
    assert.deepStrictEqual([s.metric, s.value, s.source], ['heart_rate', 52, null]);
  },
  'uploads are split into pieces': () => {
    assert.deepStrictEqual(c.chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
  },
  'weight shows in the units from Settings': () => {
    assert.strictEqual(w.weightText(72.1, 'imperial'), '159 lb');
    assert.strictEqual(w.weightText(72.1, 'metric'), '72.1 kg');
    assert.strictEqual(w.weightText(null, 'metric'), 'Choose');
    assert.strictEqual(w.weightInput(80, 'metric'), '80');
  },
  'typed weight becomes kg and stays in range': () => {
    assert.deepStrictEqual(w.parseWeight('159', 'imperial'), { kg: 72.1 });
    assert.deepStrictEqual(w.parseWeight('72,5', 'metric'), { kg: 72.5 });
    assert.deepStrictEqual(w.parseWeight('66', 'imperial'), { kg: 30 });  // 29.94 kg, kept inside the server's range
    assert.deepStrictEqual(w.parseWeight('', 'metric'), { kg: null });
    assert.deepStrictEqual(w.parseWeight('15', 'imperial'), { error: 'Type a weight between 66 and 660 lb.' });
    assert.deepStrictEqual(w.parseWeight('abc', 'metric'), { error: 'Type a weight between 30 and 300 kg.' });
  },
};

let failed = 0;
for (const [name, run] of Object.entries(checks)) {
  try {
    run();
    console.log(`pass  ${name}`);
  } catch (e) {
    failed += 1;
    console.log(`FAIL  ${name}\n      ${e.message}`);
  }
}
console.log(failed ? `${failed} failed` : 'all passed');
process.exit(failed ? 1 : 0);
