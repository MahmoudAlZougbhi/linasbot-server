/** Attachment pick helpers for Owner Copilot V2 (lazy-require Expo modules). */

export type PendingFile = { uri: string; name: string; mimeType: string };

export async function pickImageAttachment(): Promise<PendingFile | null> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const ImagePicker = require('expo-image-picker') as typeof import('expo-image-picker');
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return null;
    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.9,
    });
    if (picked.canceled || !picked.assets?.[0]) return null;
    const asset = picked.assets[0];
    return {
      uri: asset.uri,
      name: asset.fileName || 'photo.jpg',
      mimeType: asset.mimeType || 'image/jpeg',
    };
  } catch {
    return null;
  }
}

export async function pickDocumentAttachment(): Promise<PendingFile | null> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const DocumentPicker = require('expo-document-picker') as typeof import('expo-document-picker');
    const picked = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      copyToCacheDirectory: true,
    });
    if (picked.canceled || !picked.assets?.[0]) return null;
    const asset = picked.assets[0];
    return {
      uri: asset.uri,
      name: asset.name || 'document.pdf',
      mimeType: asset.mimeType || 'application/pdf',
    };
  } catch {
    return null;
  }
}
