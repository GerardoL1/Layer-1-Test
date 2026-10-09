/**
 * What the app remembers on this device: which server to talk to, whose data
 * to show, and the appearance choice. Kept in AsyncStorage so it survives restarts.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Platform } from 'react-native';

export type Appearance = 'system' | 'light' | 'dark';

type Saved = { serverUrl: string; userId: string; appearance: Appearance };

type Session = Saved & {
  loaded: boolean;
  update: (changes: Partial<Saved>) => Promise<void>;
  signOut: () => Promise<void>;
};

const KEY = 'recovery.session.v1';

// On a computer the server usually runs on the same machine. A phone needs the computer's IP.
const DEFAULTS: Saved = {
  serverUrl: Platform.OS === 'web' ? 'http://localhost:8000' : '',
  userId: '',
  appearance: 'system',
};

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [saved, setSaved] = useState<Saved>(DEFAULTS);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((text) => text && setSaved({ ...DEFAULTS, ...JSON.parse(text) }))
      .catch(() => {}) // a broken saved value just means starting from the defaults
      .finally(() => setLoaded(true));
  }, []);

  const update = useCallback(async (changes: Partial<Saved>) => {
    const next = { ...saved, ...changes };
    setSaved(next);
    await AsyncStorage.setItem(KEY, JSON.stringify(next));
  }, [saved]);

  const signOut = useCallback(() => update({ userId: '' }), [update]);

  const value = useMemo(() => ({ ...saved, loaded, update, signOut }), [saved, loaded, update, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const s = useContext(SessionContext);
  if (!s) throw new Error('useSession must be used inside SessionProvider');
  return s;
}
