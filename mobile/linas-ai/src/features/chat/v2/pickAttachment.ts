/** Attachment pick helpers for Owner Copilot V2 (lazy-require Expo modules). */

export type PendingFile = { uri: string; name: string; mimeType: string; id: string };

const MAX_IMAGES = 8;

function makeId(): string {
  return `pf_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function assetToPending(asset: {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
  name?: string | null;
}): PendingFile {
  return {
    id: makeId(),
    uri: asset.uri,
    name: asset.fileName || asset.name || 'photo.jpg',
    mimeType: asset.mimeType || 'image/jpeg',
  };
}

/** Multi-select photo library (ChatGPT-style). Returns [] if cancelled or denied. */
export async function pickImageAttachments(existingCount = 0): Promise<PendingFile[]> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const ImagePicker = require('expo-image-picker') as typeof import('expo-image-picker');
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return [];
    const remaining = Math.max(1, MAX_IMAGES - existingCount);
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
      allowsMultipleSelection: true,
      selectionLimit: remaining,
    });
    if (picked.canceled || !picked.assets?.length) return [];
    return picked.assets.slice(0, remaining).map((asset) => assetToPending(asset));
  } catch {
    return [];
  }
}

/** @deprecated Prefer pickImageAttachments — kept for single-call sites. */
export async function pickImageAttachment(): Promise<PendingFile | null> {
  const files = await pickImageAttachments(0);
  return files[0] ?? null;
}

export async function pickDocumentAttachment(): Promise<PendingFile | null> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const DocumentPicker = require('expo-document-picker') as typeof import('expo-document-picker');
    const picked = await DocumentPicker.getDocumentAsync({
      type: [
        'application/pdf',
        'image/*',
        'text/plain',
        'text/markdown',
        'application/json',
      ],
      copyToCacheDirectory: true,
    });
    if (picked.canceled || !picked.assets?.[0]) return null;
    const asset = picked.assets[0];
    return {
      id: makeId(),
      uri: asset.uri,
      name: asset.name || 'document.pdf',
      mimeType: asset.mimeType || 'application/pdf',
    };
  } catch {
    return null;
  }
}

export function isImageMime(mime: string): boolean {
  return mime.startsWith('image/');
}

export { MAX_IMAGES };
