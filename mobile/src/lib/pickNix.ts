/**
 * Picks a Nix export on iPhone with the system file picker (Files, iCloud Drive, AirDrop downloads).
 * The web version is pickNix.web.ts. Both have the same exports.
 */
import * as DocumentPicker from 'expo-document-picker';

import type { UploadFile } from '../api/client';

export const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/** The chosen file, or null if the person cancels. Only Excel files can be picked. */
export async function pickNix(): Promise<UploadFile | null> {
  const result = await DocumentPicker.getDocumentAsync({ type: XLSX, copyToCacheDirectory: true });
  const asset = result.canceled ? null : result.assets[0];
  if (!asset) return null;
  // React Native's FormData sends { uri, name, type } as a file. Its types call that a Blob.
  const part = { uri: asset.uri, name: asset.name, type: asset.mimeType ?? XLSX } as unknown as Blob;
  return { name: asset.name || 'Nix file.xlsx', part, size: asset.size };
}
