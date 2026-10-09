/**
 * Picks Light or Dark colors. Follows the phone or computer setting unless the
 * user chose one in Profile, and tells screens whether to use the wide layout.
 */
import { createContext, ReactNode, useContext, useMemo } from 'react';
import { useColorScheme, useWindowDimensions } from 'react-native';

import { useSession } from '../state/session';
import { Colors, dark, light, NARROW_BREAKPOINT, WIDE_BREAKPOINT } from './tokens';

export type Status = 'low' | 'moderate' | 'ready';

type Theme = {
  colors: Colors;
  isDark: boolean;
  isWide: boolean;
  isNarrow: boolean;
  statusColor: (s?: string | null) => string;
};

const ThemeContext = createContext<Theme | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const { appearance } = useSession();
  const { width } = useWindowDimensions();
  const isDark = appearance === 'dark' || (appearance === 'system' && system === 'dark');
  const colors = isDark ? dark : light;

  const value = useMemo<Theme>(() => ({
    colors,
    isDark,
    isWide: width >= WIDE_BREAKPOINT,
    isNarrow: width < NARROW_BREAKPOINT,
    statusColor: (s) => (s === 'low' ? colors.low : s === 'moderate' ? colors.moderate
      : s === 'ready' ? colors.ready : colors.textMuted),
  }), [colors, isDark, width]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  const t = useContext(ThemeContext);
  if (!t) throw new Error('useTheme must be used inside ThemeProvider');
  return t;
}
