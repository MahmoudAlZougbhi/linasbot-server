/** Knowledge resource pickers — reuse chat image/file helpers plus video library. */

import {
  pickDocumentAttachment,
  pickImageAttachment,
  type PendingFile,
} from '../../chat/v2/pickAttachment';

export type PickedKnowledgeFile = PendingFile & { durationSeconds?: number };

export async function pickKnowledgeImage(): Promise<PickedKnowledgeFile | null> {
  return pickImageAttachment();
}

export async function pickKnowledgeFile(): Promise<PickedKnowledgeFile | null> {
  return pickDocumentAttachment();
}

export async function pickKnowledgeVideo(): Promise<PickedKnowledgeFile | null> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const ImagePicker = require('expo-image-picker') as typeof import('expo-image-picker');
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return null;
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Videos,
      quality: 1,
      allowsMultipleSelection: false,
    });
    if (picked.canceled || !picked.assets?.[0]) return null;
    const asset = picked.assets[0];
    const name = asset.fileName || 'video.mp4';
    const durationMs = typeof asset.duration === 'number' ? asset.duration : 0;
    return {
      id: `pf_${Date.now().toString(36)}`,
      uri: asset.uri,
      name,
      mimeType: asset.mimeType || 'video/mp4',
      durationSeconds: durationMs > 0 ? Math.round(durationMs / 1000) : undefined,
    };
  } catch {
    return null;
  }
}
