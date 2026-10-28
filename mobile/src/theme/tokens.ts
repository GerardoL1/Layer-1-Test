/**
 * Design tokens from the Figma "Refresh" variables (Foundations page, Light and Dark modes).
 * The app keeps its older names, each mapped to the Refresh colour that does the same job.
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
  moderate: string;
  low: string;
  hrv: string;
  rhr: string;
  sleep: string;
  sleepDeep: string;
  sleepCore: string;
  sleepRem: string;
  baseline: string;
  sweat: string;
  infoTint: string;
  warningTint: string;
};

// Refresh name for each: canvas = ground, accent = primary (filled buttons), low = negative (errors too),
// borderStrong = control (secondary button outline), charts use chart-ink, chart-grey and the teal accent.
export const light: Colors = {
  canvas: '#FFFFFF',
  surface: '#F1F4F4',
  surfaceMuted: '#F1F4F4',
  inverse: '#1D201F',
  textPrimary: '#1D201F',
  textSecondary: '#5D6362',
  textMuted: '#5D6362',
  border: '#E6EAEA',
  borderStrong: '#D6DBDB',
  accent: '#1D201F',
  onAccent: '#FFFFFF',
  ready: '#247B50',
  moderate: '#9A4A0B',
  low: '#B42318',
  hrv: '#1D201F',
  rhr: '#1D201F',
  sleep: '#1D201F',
  sleepDeep: '#1D201F',
  sleepCore: '#9AA09F',
  sleepRem: '#1B6E66',
  baseline: '#E2ECEA',
  sweat: '#9AA09F',
  infoTint: '#E3F0EE',
  warningTint: '#FBF1E4',
};

export const dark: Colors = {
  canvas: '#0E0F0F',
  surface: '#1B1D1D',
  surfaceMuted: '#1B1D1D',
  inverse: '#F2F4F3',
  textPrimary: '#F2F4F3',
  textSecondary: '#A8AEAD',
  textMuted: '#A8AEAD',
  border: '#2B2E2E',
  borderStrong: '#4A4E4E',
  accent: '#F2F4F3',
  onAccent: '#0E0F0F',
  ready: '#46C07F',
  moderate: '#E3A457',
  low: '#EF6F6A',
  hrv: '#F2F4F3',
  rhr: '#F2F4F3',
  sleep: '#F2F4F3',
  sleepDeep: '#F2F4F3',
  sleepCore: '#5C6261',
  sleepRem: '#62BDB1',
  baseline: '#20302E',
  sweat: '#5C6261',
  infoTint: '#18302D',
  warningTint: '#2B2117',
};

export const fonts = {
  serif: 'InstrumentSerif_400Regular',
  sans: 'InstrumentSans_400Regular',
  sansMedium: 'InstrumentSans_500Medium',
  sansSemiBold: 'InstrumentSans_600SemiBold',
};

// Refresh text styles from Figma: size, line height and letter spacing (Figma gives it in % of the size).
const t = (fontFamily: string, fontSize: number, lineHeight: number, spacingPct = 0) => ({
  fontFamily,
  fontSize,
  lineHeight,
  letterSpacing: (fontSize * spacingPct) / 100,
});

// The old names are kept so every screen picks up the new look without changes.
// Instrument Serif is only for greetings and page titles, everything else is Instrument Sans.
export const type = {
  greetingLarge: t(fonts.serif, 48, 52, -1.5),
  greeting: t(fonts.serif, 32, 36, -1),
  scoreHero: t(fonts.sans, 48, 52, -1.5),
  scoreSuffix: t(fonts.sans, 22, 28, -1),
  scoreMetric: t(fonts.sans, 32, 36, -1.5),
  h1: t(fonts.serif, 32, 36, -1),
  h2: t(fonts.sans, 24, 30, -1),
  h3: t(fonts.sansSemiBold, 15, 22),
  bodyLarge: t(fonts.sans, 18, 26, -0.5),
  bodyEmphasis: t(fonts.sansMedium, 15, 22),
  body: t(fonts.sans, 15, 22),
  bodySmall: t(fonts.sans, 13, 18, 0.2),
  button: t(fonts.sansMedium, 15, 20),
  // Labels used to be small uppercase mono. The redesign names things in sentence case at reading size.
  labelMedium: t(fonts.sansMedium, 13, 18, 0.2),
  labelSmall: t(fonts.sansMedium, 13, 18, 0.2),
};

export const space = { 4: 4, 8: 8, 12: 12, 16: 16, 20: 20, 24: 24, 32: 32, 48: 48 } as const;
// Refresh shapes: inputs 14, rows 16, panels 22, buttons, chips and tags fully round.
export const radius = { sm: 14, md: 16, lg: 22, full: 999 } as const;

// Below this width the app uses the iPhone layout (tab bar), above it the computer layout (sidebar).
export const WIDE_BREAKPOINT = 768;
// Below this width (iPhone SE 1st gen and similar, 320 px) a few things get shorter or smaller to fit.
export const NARROW_BREAKPOINT = 360;
