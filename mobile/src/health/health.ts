/**
 * Apple Health only exists on iPhone. On the web (computer view) these do nothing,
 * and data comes from an imported Health export instead.
 * Keep the exports the same as health.ios.ts.
 */
export type SyncResult = { read: number; added: number; message: string };

export const healthAvailable = () => false;

export async function connectHealth(): Promise<void> {
  throw new Error('Apple Health is only available in the iPhone app.');
}

export async function syncHealth(_serverUrl: string, _userId: string): Promise<SyncResult> {
  return { read: 0, added: 0, message: '' };
}

export function watchHealth(_onChange: () => void): () => void {
  return () => {};
}
