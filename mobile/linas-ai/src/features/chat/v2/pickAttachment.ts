/** Attachment pick helpers for Owner Copilot V2 (lazy-require Expo modules). */

export type PendingFile = { uri: string; name: string; mimeType: string; id: string };

const MAX_IMAGES = 8;

function makeId(): string {
  return `pf_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function mimeFromName(name: string, fallback: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  const byExt: Record<string, string> = {
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    heic: 'image/heic',
    heif: 'image/heif',
    pdf: 'application/pdf',
    txt: 'text/plain',
    md: 'text/markdown',
    csv: 'text/csv',
    json: 'application/json',
    doc: 'application/msword',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    xls: 'application/vnd.ms-excel',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  };
  return byExt[ext] || fallback;
}

function resolveMime(name: string, raw: string | null | undefined, fallback: string): string {
  const mime = (raw || '').trim();
  if (!mime || mime === 'application/octet-stream') return mimeFromName(name, fallback);
  return mime;
}

function assetToPending(asset: {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
  name?: string | null;
}): PendingFile {
  const name = asset.fileName || asset.name || 'photo.jpg';
  return {
    id: makeId(),
    uri: asset.uri,
    name,
    mimeType: resolveMime(name, asset.mimeType, 'image/jpeg'),
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
    // '*/*' — a MIME array with invalid iOS UTIs (e.g. text/markdown) makes
    // getDocumentAsync throw, which this helper used to swallow as a no-op.
    const picked = await DocumentPicker.getDocumentAsync({
      type: '*/*',
      copyToCacheDirectory: true,
    });
    if (picked.canceled || !picked.assets?.[0]) return null;
    const asset = picked.assets[0];
    const name = asset.name || 'document.pdf';
    return {
      id: makeId(),
      uri: asset.uri,
      name,
      mimeType: resolveMime(name, asset.mimeType, 'application/octet-stream'),
    };
  } catch {
    return null;
  }
}

export async function pickVideoAttachment(): Promise<PendingFile | null> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const ImagePicker = require('expo-image-picker') as typeof import('expo-image-picker');
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return null;
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Videos,
      quality: 0.8,
      allowsMultipleSelection: false,
    });
    if (picked.canceled || !picked.assets?.[0]) return null;
    const asset = picked.assets[0];
    return assetToPending({
      uri: asset.uri,
      fileName: asset.fileName || 'video.mp4',
      mimeType: asset.mimeType || 'video/mp4',
    });
  } catch {
    return null;
  }
}

export function isImageMime(mime: string): boolean {
  return mime.startsWith('image/');
}

export { MAX_IMAGES };
