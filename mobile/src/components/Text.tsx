import { Text as RNText, TextProps } from 'react-native';

import { useTheme } from '../theme/theme';
import { Colors, type as typeStyles } from '../theme/tokens';

type Props = TextProps & {
  variant?: keyof typeof typeStyles;
  color?: keyof Colors;
};

/** Text in one of the Figma text styles. Defaults to Body/Regular in the primary text color. */
export function Text({ variant = 'body', color = 'textPrimary', style, ...rest }: Props) {
  const { colors } = useTheme();
  return <RNText {...rest} style={[typeStyles[variant], { color: colors[color] }, style]} />;
}
