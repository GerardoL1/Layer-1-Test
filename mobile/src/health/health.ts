/**
 * Apple Health only exists on iPhone. On the web (computer view) these do nothing,
 * and data comes from an imported Health export instead.
 */
export const healthAvailable = () => false;

export async function connectHealth(): Promise<void> {
  throw new Error('Apple Health is only available in the iPhone app.');
}

export async function sendLastDay(_serverUrl: string, _userId: string): Promise<string> {
  throw new Error('Apple Health is only available in the iPhone app.');
}
