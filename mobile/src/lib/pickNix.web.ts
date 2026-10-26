/**
 * Picks a Nix export in the browser. Same exports as pickNix.ts, which is the iPhone version.
 */
import type { UploadFile } from '../api/client';
import { pickFile } from './pickFile';

export const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/** The chosen file, or null if the person cancels. */
export async function pickNix(): Promise<UploadFile | null> {
  const file = await pickFile(`.xlsx,${XLSX}`);
  return file ? { name: file.name, part: file, size: file.size } : null;
}
