/**
 * On iPhone there's no export file to drop, since data comes from Apple Health directly.
 * Keep the props the same as DropZone.web.tsx.
 */
type Props = { onFile: (file: File) => void; disabled?: boolean; note?: string; title?: string; accept?: string };

export function DropZone(_props: Props) {
  return null;
}
