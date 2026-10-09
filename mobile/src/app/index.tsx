import { Redirect } from 'expo-router';

import { useSession } from '../state/session';

/** First stop: people who haven't picked a server and tester yet go through Setup. */
export default function Start() {
  const { serverUrl, userId } = useSession();
  return <Redirect href={serverUrl && userId ? '/today' : '/setup'} />;
}
