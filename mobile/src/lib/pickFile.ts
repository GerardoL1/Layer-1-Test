/** On iPhone, data comes from Apple Health directly, so there's no export to pick. */
export async function pickFile(_accept: string): Promise<File | null> {
  return null;
}

export const canPickFile = false;
