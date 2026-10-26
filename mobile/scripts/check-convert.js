/**
 * Checks src/health/convert.ts (HealthKit sample -> server upload) and src/lib/weight.ts (kg and lb)
 * without an iPhone.
 * Uses the TypeScript compiler the app already has, so no test framework is needed.
 *
 *   npm test
 */
// A time zone with clock changes, so date maths that assumes 24-hour days fails here and in CI (which runs in UTC).
process.env.TZ = 'America/Chicago';
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
const s = load('lib', 'sweat.ts');

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
  'the heaviest weights still show a value the box accepts': () => {
    assert.strictEqual(w.weightInput(300, 'imperial'), '660');
    assert.deepStrictEqual(w.parseWeight(w.weightInput(300, 'imperial'), 'imperial'), { kg: 299.4 });
  },
  'a trailing or leading dot is fine': () => {
    assert.deepStrictEqual(w.parseWeight('72.', 'metric'), { kg: 72 });
    assert.deepStrictEqual(w.parseWeight('.5', 'metric'), { error: 'Type a weight between 30 and 300 kg.' });
    assert.deepStrictEqual(w.parseWeight('150.', 'imperial'), { kg: 68 });
  },
  'sweat amounts show in the units from Settings': () => {
    assert.deepStrictEqual(s.fluid(640, 'metric'), { value: '640', unit: 'ml' });
    assert.deepStrictEqual(s.fluid(1400, 'metric'), { value: '1.4', unit: 'L' });
    assert.deepStrictEqual(s.fluid(62, 'imperial'), { value: '2.1', unit: 'oz' });
    assert.deepStrictEqual(s.fluid(1400, 'imperial'), { value: '47', unit: 'oz' });
    assert.deepStrictEqual(s.rate(1.45, 'metric'), { value: '1.45', unit: 'L/h' });
    assert.deepStrictEqual(s.rate(1.45, 'imperial'), { value: '49', unit: 'oz/h' });
    assert.deepStrictEqual(s.sodium(1150), { value: '1,150', unit: 'mg' });
  },
  'rehydrate amounts are rounded the way people pour': () => {
    assert.strictEqual(s.about(2100, 'metric'), 'around 2 L');
    assert.strictEqual(s.about(2300, 'metric'), 'around 2.5 L');
    assert.strictEqual(s.about(640, 'metric'), 'around 600 ml');
    assert.strictEqual(s.about(30, 'metric'), 'around 100 ml');
    assert.strictEqual(s.about(2100, 'imperial'), 'around 71 oz');
  },
  'durations and workout times': () => {
    assert.strictEqual(s.duration(35), '35 min');
    assert.strictEqual(s.duration(74), '1 h 14 min');
    assert.strictEqual(s.duration(120), '2 h');
    assert.strictEqual(s.startLabel('2026-09-30T07:05'), 'Wed 30 Sep · 7:05 AM');
    assert.strictEqual(s.spanLabel('2026-09-29T18:10', '2026-09-29T19:08'), 'Tue 29 Sep · 6:10–7:08 PM');
    assert.strictEqual(s.spanLabel('2026-09-29T11:30', '2026-09-29T12:15'), 'Tue 29 Sep · 11:30 AM–12:15 PM');
    assert.strictEqual(s.sourceText('apple_health'), 'Apple Watch');
    assert.strictEqual(s.sourceText('patch'), 'Started in the app');
  },
  'workouts in this week, last week and by month, newest first': () => {
    const at = (start_local) => ({ start_local });
    const all = ['2026-09-15T18:05', '2026-09-30T18:05', '2026-09-27T10:20', '2026-09-29T18:10', '2025-12-30T08:00']
      .map(at);
    const got = s.sections(all, '2026-10-01T08:30').map((x) => [x.title, x.items.map((w) => w.start_local)]);
    assert.deepStrictEqual(got, [
      ['This week', ['2026-09-30T18:05', '2026-09-29T18:10']],
      ['Last week', ['2026-09-27T10:20']],
      ['September', ['2026-09-15T18:05']],
      ['December 2025', ['2025-12-30T08:00']],
    ]);
    const week = s.lastSevenDays(all, '2026-10-01T08:30').map((w) => w.start_local);
    assert.deepStrictEqual(week, ['2026-09-30T18:05', '2026-09-29T18:10', '2026-09-27T10:20']);
  },
  'amounts just under a litre or 10 oz pick the unit after rounding': () => {
    assert.strictEqual(s.about(960, 'metric'), 'around 1 L');
    assert.strictEqual(s.about(999, 'metric'), 'around 1 L');
    assert.deepStrictEqual(s.fluid(999.5, 'metric'), { value: '1.0', unit: 'L' });
    assert.deepStrictEqual(s.fluid(9.97 * 29.5735, 'imperial'), { value: '10', unit: 'oz' });
  },
  'the last 7 days keep their oldest day when clocks go back': () => {
    // 1 Nov 2026 is 25 hours long in the US. Only matters where the computer running this has that time zone,
    // but the count is by calendar day either way.
    const at = (start_local) => ({ start_local });
    const got = s.lastSevenDays([at('2026-10-30T10:00'), at('2026-10-31T10:00')], '2026-11-05T08:00');
    assert.deepStrictEqual(got.map((w) => w.start_local), ['2026-10-31T10:00', '2026-10-30T10:00']);
  },
  'time ranges show the day change and single moments': () => {
    assert.strictEqual(s.spanLabel('2026-09-29T23:30', '2026-09-30T00:30'), 'Tue 29 Sep · 11:30 PM – Wed 30 Sep 12:30 AM');
    assert.strictEqual(s.spanLabel('2026-09-29T08:00', '2026-09-29T08:00'), 'Tue 29 Sep · 8:00 AM');
  },
  'future workouts go under Upcoming': () => {
    const got = s.sections([{ start_local: '2026-10-20T08:00' }, { start_local: '2026-09-30T08:00' }], '2026-10-01T08:30');
    assert.deepStrictEqual(got.map((x) => x.title), ['Upcoming', 'This week']);
  },
  'bad numbers and dates show a dash, not NaN': () => {
    assert.deepStrictEqual(s.fluid(NaN, 'metric'), { value: '–', unit: '' });
    assert.deepStrictEqual(s.fluid(-5, 'metric'), { value: '–', unit: '' });
    assert.deepStrictEqual(s.rate(-1, 'imperial'), { value: '–', unit: '' });
    assert.deepStrictEqual(s.sodium(NaN), { value: '–', unit: '' });
    assert.strictEqual(s.about(0, 'metric'), null);
    assert.strictEqual(s.about(NaN, 'imperial'), null);
    assert.strictEqual(s.duration(NaN), '–');
    assert.strictEqual(s.startLabel('not a date'), '–');
    assert.deepStrictEqual(s.sections([{ start_local: 'garbage' }], '2026-10-01T08:30').map((x) => x.title), ['Unknown date']);
  },
  'durations read out in words': () => {
    assert.strictEqual(s.durationWords(74), '1 hour 14 minutes');
    assert.strictEqual(s.durationWords(120), '2 hours');
    assert.strictEqual(s.durationWords(1), '1 minute');
  },
  'no-sweat sessions show breathing loss, muted, with no sodium': () => {
    const dry = { sweat_detected: false, fluid_loss_ml: 27, sweat_rate_l_h: 0.03, sodium_mg: null };
    assert.deepStrictEqual(s.sessionStats(dry, 'metric'), [
      { label: 'Breathing loss', shown: { value: '27', unit: 'ml' }, tone: 'muted' },
      { label: 'Breathing rate', shown: { value: '0.03', unit: 'L/h' }, tone: 'muted' },
    ]);
    const wet = { sweat_detected: true, fluid_loss_ml: 1400, sweat_rate_l_h: 1.45, sodium_mg: null };
    assert.deepStrictEqual(s.sessionStats(wet, 'metric').map((x) => [x.label, x.shown && x.shown.value, x.tone]), [
      ['Fluid lost', '1.4', 'sweat'],
      ['Sweat rate', '1.45', 'sweat'],
      ['Sodium lost', null, 'sweat'],
    ]);
  },
  'the suggestion follows the readiness status, and needs one': () => {
    assert.strictEqual(s.suggestion('low').effort, 'Easy');
    assert.strictEqual(s.suggestion('ready').title, 'Good day to train hard.');
    assert.strictEqual(s.suggestion('building_baseline'), null);
    assert.strictEqual(s.suggestion(null), null);
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
