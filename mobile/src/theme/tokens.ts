/**
 * Design tokens copied from the Figma Foundations page ("Field notes" style).
 * Light = "Graph paper", Dark = "Midnight". Change a value here and every screen follows.
 */

export type Colors = {
  canvas: string;
  surface: string;
  surfaceMuted: string;
  inverse: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  border: string;
  borderStrong: string;
  accent: string;
  onAccent: string;
  ready: string;
  readyBg: string;
  moderate: string;
  moderateBg: string;
  low: string;
  lowBg: string;
  hrv: string;
  rhr: string;
  sleep: string;
  sleepDeep: string;
  sleepCore: string;
  sleepRem: string;
  baseline: string;
};

export const light: Colors = {
  canvas: '#E4EAF0',
  surface: '#EEF2F6',
  surfaceMuted: '#D3DCE6',
  inverse: '#132036',
  textPrimary: '#132036',
  textSecondary: '#46536A',
  textMuted: '#6B7790',
  border: '#C2CCD8',
  borderStrong: '#132036',
  accent: '#1F3C88',
  onAccent: '#E4EAF0',
  ready: '#1E7466',
  readyBg: '#D3E6E2',
  moderate: '#A9741A',
  moderateBg: '#EFE3CC',
  low: '#B5306B',
  lowBg: '#F0D6E1',
  hrv: '#132036',
  rhr: '#7A5C2E',
  sleep: '#3E4F9E',
  sleepDeep: '#26336E',
  sleepCore: '#6C7CC4',
  sleepRem: '#A9B5E6',
  baseline: '#D3DCE6',
};

export const dark: Colors = {
  canvas: '#101826',
  // Figma has no Midnight value for these, so they're picked to sit between canvas and text.
  surface: '#172133',
  inverse: '#E9E6DC',
  readyBg: '#1C3A35',
  moderateBg: '#3B3420',
  lowBg: '#3F2A22',
  hrv: '#E9E6DC',
  rhr: '#D2AE74',
  sleep: '#8E9BE6',
  baseline: '#1D2738',
  // From Figma.
  surfaceMuted: '#1D2738',
  textPrimary: '#E9E6DC',
  textSecondary: '#B4B3AE',
  textMuted: '#7E8594',
  border: '#2A3445',
  borderStrong: '#E9E6DC',
  accent: '#9DB8F2',
  onAccent: '#101826',
  ready: '#6CC198',
  moderate: '#E2C15A',
  low: '#F08A4B',
  sleepDeep: '#5F6BC0',
  sleepCore: '#8E9BE6',
  sleepRem: '#C2CBF5',
};

export const fonts = {
  heading: 'Fraunces_600SemiBold',
  body: 'IBMPlexSans_400Regular',
  bodyMedium: 'IBMPlexSans_500Medium',
  bodySemiBold: 'IBMPlexSans_600SemiBold',
  number: 'IBMPlexSansCondensed_600SemiBold',
  numberRegular: 'IBMPlexSansCondensed_400Regular',
  label: 'IBMPlexMono_500Medium',
};

// Text styles from Figma. lineHeight there is a multiple, here it's in points.
const t = (fontFamily: string, fontSize: number, lineHeight: number, extra: object = {}) => ({
  fontFamily,
  fontSize,
  lineHeight: Math.round(fontSize * lineHeight),
  ...extra,
});

export const type = {
  scoreHero: t(fonts.number, 168, 0.86),
  scoreSuffix: t(fonts.numberRegular, 24, 1.1),
  scoreMetric: t(fonts.number, 30, 1.1),
  h1: t(fonts.heading, 30, 1.12),
  h2: t(fonts.heading, 21, 1.25),
  h3: t(fonts.heading, 18, 1.3),
  bodyLarge: t(fonts.body, 16, 1.45),
  bodyEmphasis: t(fonts.bodyMedium, 16, 1.3),
  body: t(fonts.body, 15, 1.45),
  bodySmall: t(fonts.body, 12, 1.4),
  button: t(fonts.bodySemiBold, 15, 1.2),
  // Labels are always uppercase.
  labelMedium: t(fonts.label, 11, 1.2, { textTransform: 'uppercase' as const, letterSpacing: 0.4 }),
  labelSmall: t(fonts.label, 10, 1.2, { textTransform: 'uppercase' as const, letterSpacing: 0.4 }),
};

export const space = { 4: 4, 8: 8, 12: 12, 16: 16, 20: 20, 24: 24, 32: 32, 48: 48 } as const;
export const radius = { sm: 2, md: 3, lg: 4 } as const;

// Below this width the app uses the iPhone layout (tab bar), above it the computer layout (sidebar).
export const WIDE_BREAKPOINT = 768;
