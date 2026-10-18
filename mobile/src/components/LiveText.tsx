import { ComponentProps, useEffect } from 'react';

import { announce } from '../lib/a11y';
import { Text } from './Text';

type Props = Omit<ComponentProps<typeof Text>, 'children'> & {
  children: string;
  /** Errors interrupt (an alert), other updates wait until the screen reader is free. */
  error?: boolean;
};

/**
 * Text a screen reader reads out when it appears or changes, for loading, progress, results and errors.
 * Without this someone who can't see the screen never learns that an import finished or a save failed.
 */
export function LiveText({ children, error, ...rest }: Props) {
  useEffect(() => announce(children), [children]);
  return (
    <Text accessibilityRole={error ? 'alert' : undefined} aria-live={error ? 'assertive' : 'polite'} {...rest}>
      {children}
    </Text>
  );
}
