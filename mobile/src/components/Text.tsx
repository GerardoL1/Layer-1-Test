import { Text as RNText, TextProps } from 'react-native';

import { headingLevel } from '../lib/a11y';
import { useTheme } from '../theme/theme';
import { Colors, type as typeStyles } from '../theme/tokens';

type Props = TextProps & {
  variant?: keyof typeof typeStyles;
  color?: keyof Colors;
};

// iPhone "Larger Text" makes text grow. The big score numbers are already large, so they're held back
// to stay on screen. Everything else can reach at least double size, as WCAG asks.
const MAX_SCALE: Partial<Record<keyof typeof typeStyles, number>> = { scoreHero: 1, scoreSuffix: 1.2, scoreMetric: 1.2 };
const DEFAULT_MAX_SCALE = 2;

/** Text in one of the Figma text styles. Defaults to Body/Regular in the primary text color. */
export function Text({ variant = 'body', color = 'textPrimary', style, ...rest }: Props) {
  const { colors } = useTheme();
  // Page titles use h1, so they're level 1. Every other heading is a section, level 2.
  const level = rest.accessibilityRole === 'header' ? (variant === 'h1' ? 1 : 2) : undefined;
  return <RNText maxFontSizeMultiplier={MAX_SCALE[variant] ?? DEFAULT_MAX_SCALE} {...headingLevel(level)} {...rest}
    style={[typeStyles[variant], { color: colors[color] }, style]} />;
}
