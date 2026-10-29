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
    assert.strictEqual(s.startLabel('2026-09-30T07:05'), 'Wed 30 Sep · 7:05 am');
    assert.strictEqual(s.spanLabel('2026-09-29T18:10', '2026-09-29T19:08'), 'Tue 29 Sep · 6:10–7:08 pm');
    assert.strictEqual(s.spanLabel('2026-09-29T11:30', '2026-09-29T12:15'), 'Tue 29 Sep · 11:30 am–12:15 pm');
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
    assert.strictEqual(s.spanLabel('2026-09-29T23:30', '2026-09-30T00:30'), 'Tue 29 Sep · 11:30 pm – Wed 30 Sep 12:30 am');
    assert.strictEqual(s.spanLabel('2026-09-29T08:00', '2026-09-29T08:00'), 'Tue 29 Sep · 8:00 am');
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
  'typed-in sweat amounts become ml, mg and L/h': () => {
    assert.deepStrictEqual(s.parseAmount('900', 'fluid', 'metric'), { value: 900 });
    assert.deepStrictEqual(s.parseAmount(' 1,150 ', 'fluid', 'metric'), { value: 1150 });
    assert.deepStrictEqual(s.parseAmount('30.5', 'fluid', 'imperial'), { value: 902 });
    assert.deepStrictEqual(s.parseAmount('1,5', 'rate', 'metric'), { value: 1.5 });
    assert.deepStrictEqual(s.parseAmount('49', 'rate', 'imperial'), { value: 1.4491 });
    assert.deepStrictEqual(s.parseAmount('640', 'sodium', 'imperial'), { value: 640 });
    assert.deepStrictEqual(s.parseAmount('', 'sodium', 'metric'), { value: null });
    assert.deepStrictEqual(s.parseAmount('  ', 'rate', 'metric'), { value: null });
  },
  'typed-in amounts outside what the server takes get a message in your units': () => {
    assert.deepStrictEqual(s.parseAmount('', 'fluid', 'metric'), { error: 'Type how much sweat you lost.' });
    assert.deepStrictEqual(s.parseAmount('0', 'fluid', 'metric'), { error: 'Type a sweat loss between 1 and 30,000 ml.' });
    assert.deepStrictEqual(s.parseAmount('2000', 'fluid', 'imperial'),
      { error: 'Type a sweat loss between 0.1 and 1,014 oz.' });
    assert.deepStrictEqual(s.parseAmount('-5', 'sodium', 'metric'),
      { error: 'Type a sodium loss between 1 and 100,000 mg, or leave it empty.' });
    assert.deepStrictEqual(s.parseAmount('0.001', 'rate', 'metric'),
      { error: 'Type a sweat rate between 0.01 and 10 L/h, or leave it empty.' });
    assert.deepStrictEqual(s.parseAmount('abc', 'rate', 'imperial'),
      { error: 'Type a sweat rate between 1 and 338 oz/h, or leave it empty.' });
    assert.deepStrictEqual(s.parseAmount('1e3', 'fluid', 'metric'), { error: 'Type a sweat loss between 1 and 30,000 ml.' });
  },
  'the smallest and largest typed-in amounts stay inside the server limits': () => {
    assert.ok(s.parseAmount('0.1', 'fluid', 'imperial').value >= 1);
    assert.ok(s.parseAmount('1014', 'fluid', 'imperial').value <= 30000);
    assert.ok(s.parseAmount('1', 'rate', 'imperial').value >= 0.01);
    assert.ok(s.parseAmount('338', 'rate', 'imperial').value <= 10);
  },
  'notes on the Check your import screen': () => {
    assert.strictEqual(s.existingNote('none'), null);
    assert.strictEqual(s.existingNote('replaces_less_precise'), 'Replaces your earlier sweat data with more precise numbers.');
    assert.strictEqual(s.existingNote('keeps_more_precise'),
      'This workout already has more precise sweat data, so saving this file won’t change it.');
    assert.strictEqual(s.notThisWorkout('2026-09-28T09:10'), 'This file is from Mon 28 Sep at 9:10 am, not this workout.');
    const all = { sweat_detected: true, electrolytes_mg: 860, electrolyte_rate_mg_h: null, sodium_rate_mg_h: 403.4,
      nix_index: 74 };
    // Shown on the preview, before anything is saved, so it says what's in the file.
    assert.strictEqual(s.alsoSaved(all), 'Also in the file: electrolytes 860 mg, sodium rate 403 mg/h, Nix index 74.');
    assert.strictEqual(s.alsoSaved({ ...all, electrolytes_mg: null, sodium_rate_mg_h: null, nix_index: null }), null);
  },
  'a comma after a leading zero is a decimal, not thousands': () => {
    assert.deepStrictEqual(s.parseAmount('0,500', 'rate', 'metric'), { value: 0.5 });
    assert.deepStrictEqual(s.parseAmount('0,5', 'fluid', 'imperial'), { value: 14.8 });
    assert.deepStrictEqual(s.parseAmount('0,500', 'fluid', 'imperial'), { value: 14.8 });
    assert.deepStrictEqual(s.parseAmount('1,500', 'fluid', 'metric'), { value: 1500 });
  },
  'notes for keeping sweat data and moving a file off another workout': () => {
    assert.strictEqual(s.existingNote('keeps_sweat_data'),
      'This workout already has sweat data, and Nix picked up no sweat in this file, so saving won’t change it.');
    assert.strictEqual(s.movesNote('Thu 25 Sep · Leg day'),
      'This file is saved on Thu 25 Sep · Leg day. Saving here moves it off that workout.');
    assert.strictEqual(s.isRefused('keeps_sweat_data'), true);
    assert.strictEqual(s.isRefused('keeps_more_precise'), true);
    assert.strictEqual(s.isRefused('replaces'), false);
  },
  'typed-in numbers already saved fill the boxes in your units': () => {
    assert.strictEqual(s.amountInput(900, 'fluid', 'metric'), '900');
    assert.strictEqual(s.amountInput(900, 'fluid', 'imperial'), '30.4');
    assert.strictEqual(s.amountInput(1.2, 'rate', 'metric'), '1.2');
    assert.strictEqual(s.amountInput(1.2, 'rate', 'imperial'), '41');
    assert.strictEqual(s.amountInput(410, 'sodium', 'imperial'), '410');
    assert.strictEqual(s.amountInput(null, 'sodium', 'metric'), '');
    // What a box shows reads back to (about) the same stored value.
    assert.deepStrictEqual(s.parseAmount(s.amountInput(900, 'fluid', 'imperial'), 'fluid', 'imperial'), { value: 899 });
  },
  'example values fit the unit': () => {
    assert.strictEqual(s.amountHint('rate', 'metric'), 'e.g. 1.2');
    assert.strictEqual(s.amountHint('rate', 'imperial'), 'e.g. 40');
    assert.strictEqual(s.amountHint('fluid', 'imperial'), 'e.g. 30');
  },
  'only workouts with real sweat data get the SWEAT tag': () => {
    const ids = s.sweatWorkoutIds([
      { workout_id: 'wet', sweat_detected: true },
      { workout_id: 'dry', sweat_detected: false },
      { workout_id: null, sweat_detected: true },
    ]);
    assert.deepStrictEqual([...ids], ['wet']);
  },
  'a box left as it was keeps the exact saved number': () => {
    // 640 ml shows as 21.6 oz, and reading 21.6 oz back gives 638.8 ml, so untouched boxes keep 640.
    assert.deepStrictEqual(s.typedValue('21.6', 'fluid', 'imperial', 640), { value: 640 });
    assert.deepStrictEqual(s.typedValue('22', 'fluid', 'imperial', 640), { value: 650.6 });
    assert.deepStrictEqual(s.typedValue('', 'sodium', 'metric', 410), { value: null });
    assert.deepStrictEqual(s.typedValue('900', 'fluid', 'metric', null), { value: 900 });
  },
  'Check your import uses Figma labels for the numbers': () => {
    assert.strictEqual(s.checkLabel('Fluid lost'), 'Sweat loss');
    assert.strictEqual(s.checkLabel('Sodium lost'), 'Sodium loss');
    assert.strictEqual(s.checkLabel('Sweat rate'), 'Sweat rate');
    assert.strictEqual(s.checkLabel('Breathing loss'), 'Breathing loss');
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
