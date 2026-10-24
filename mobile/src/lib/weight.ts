/**
 * Body weight. The server keeps kg, and the app shows kg or lb following Settings → Units.
 * No imports, so scripts/check-convert.js can test it without an iPhone.
 */
export type Units = 'metric' | 'imperial';

const LB_PER_KG = 2.20462;
// The server accepts 30 to 300 kg. In pounds that's about 66 to 660.
const LIMITS = { metric: { lo: 30, hi: 300, unit: 'kg' }, imperial: { lo: 66, hi: 660, unit: 'lb' } } as const;

export function weightUnit(units: Units): 'kg' | 'lb' {
  return LIMITS[units].unit;
}

/** What the box shows: "159" in pounds, "72.4" in kg, empty when there's no weight yet. */
export function weightInput(kg: number | null | undefined, units: Units): string {
  if (kg === null || kg === undefined) return '';
  // 300 kg is 661.4 lb, so the shown pounds are kept inside the range the box accepts.
  if (units === 'imperial') return String(Math.min(660, Math.max(66, Math.round(kg * LB_PER_KG))));
  return String(Math.round(kg * 10) / 10);
}

/** What a row shows: "159 lb", "72.4 kg", or "Choose". */
export function weightText(kg: number | null | undefined, units: Units): string {
  const v = weightInput(kg, units);
  return v ? `${v} ${weightUnit(units)}` : 'Choose';
}

/** Typed text to kg. An empty box clears the weight. Accepts "72,5" decimals. */
export function parseWeight(text: string, units: Units): { kg: number | null } | { error: string } {
  const t = text.trim().replace(',', '.');
  if (!t) return { kg: null };
  const { lo, hi, unit } = LIMITS[units];
  // "72", "72.5", "72." and ".5" are all fine.
  const n = /^(\d+\.?\d*|\.\d+)$/.test(t) ? Number(t) : NaN;
  if (!(n >= lo && n <= hi)) return { error: `Type a weight between ${lo} and ${hi} ${unit}.` };
  const kg = Math.round((units === 'imperial' ? n / LB_PER_KG : n) * 10) / 10;
  // 66 lb is 29.94 kg. Rounding can land a hair outside the server's range, so keep it inside.
  return { kg: Math.min(300, Math.max(30, kg)) };
}
