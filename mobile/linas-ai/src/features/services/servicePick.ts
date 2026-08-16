/** Service media pickers — reuse chat image/file helpers plus video library. */

import {
  pickDocumentAttachment,
  pickImageAttachment,
  type PendingFile,
} from '../chat/v2/pickAttachment';

export type PickedServiceFile = PendingFile & { durationSeconds?: number };

export async function pickServiceImage(): Promise<PickedServiceFile | null> {
  return pickImageAttachment();
}

export async function pickServiceFile(): Promise<PickedServiceFile | null> {
  return pickDocumentAttachment();
}

export async function pickServiceVideo(): Promise<PickedServiceFile | null> {
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
    const durationRaw = typeof asset.duration === 'number' ? asset.duration : 0;
    const durationSeconds =
      durationRaw > 1000 ? Math.round(durationRaw / 1000) : durationRaw > 0 ? Math.round(durationRaw) : undefined;
    return {
      id: `pf_${Date.now().toString(36)}`,
      uri: asset.uri,
      name,
      mimeType: asset.mimeType || 'video/mp4',
      durationSeconds,
    };
  } catch {
    return null;
  }
}
