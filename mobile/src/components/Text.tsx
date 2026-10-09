import { Text as RNText, TextProps } from 'react-native';

import { useTheme } from '../theme/theme';
import { Colors, type as typeStyles } from '../theme/tokens';

type Props = TextProps & {
  variant?: keyof typeof typeStyles;
  color?: keyof Colors;
};

// iPhone "Larger Text" makes text grow. Big score numbers stay fixed so they never run off the screen,
// everything else grows up to 1.4x so it stays readable without breaking the layout.
const MAX_SCALE: Partial<Record<keyof typeof typeStyles, number>> = { scoreHero: 1, scoreSuffix: 1.2, scoreMetric: 1.2 };

/** Text in one of the Figma text styles. Defaults to Body/Regular in the primary text color. */
export function Text({ variant = 'body', color = 'textPrimary', style, ...rest }: Props) {
  const { colors } = useTheme();
  return <RNText maxFontSizeMultiplier={MAX_SCALE[variant] ?? 1.4} {...rest}
    style={[typeStyles[variant], { color: colors[color] }, style]} />;
}
