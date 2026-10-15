/**
 * The inline settings editors on Profile and in Setup: which row is open, saving a change,
 * and the error to show under the open row.
 */
import { useState } from 'react';

import { SettingsUpdate } from '../../api/client';
import { useApi } from '../../api/useApi';
import { errorText } from '../../lib/useLoad';

/** saved() runs after each successful save, usually to reload the screen. */
export function useSettingsEditor(saved: () => void) {
  const api = useApi();
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggle = (key: string) => {
    setError(null);
    setOpen(open === key ? null : key);
  };

  /** close: false keeps the row open, for editors where you pick several things (training days). */
  async function save(changes: SettingsUpdate, close = true) {
    setError(null);
    try {
      await api.saveSettings(changes);
      if (close) setOpen(null);
      saved();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return { open, toggle, save, error, isOpen: (key: string) => open === key };
}
