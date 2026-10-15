import { useMemo } from 'react';

import { useSession } from '../state/session';
import { makeApi } from './client';

/** The API for the server and tester picked in the session. A new object when either changes. */
export function useApi() {
  const { serverUrl, userId } = useSession();
  return useMemo(() => makeApi(serverUrl, userId), [serverUrl, userId]);
}
