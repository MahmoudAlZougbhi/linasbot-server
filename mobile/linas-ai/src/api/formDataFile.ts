import { File as ExpoFile, Paths } from 'expo-file-system';
import { copyAsync, getInfoAsync } from 'expo-file-system/legacy';

/**
 * Expo SDK 57 installs expo/fetch as global fetch. That converter rejects React
 * Native's `{ uri, name, type }` FormData parts with:
 * "Unsupported FormDataPart implementation".
 *
 * Append a local file via expo-file-system `File` (Blob-compatible with bytes()).
 */
export function appendLocalFile(
  form: FormData,
  fieldName: string,
  uri: string,
  options: { name: string },
): void {
  const trimmed = uri.trim();
  if (!trimmed) {
    throw new Error('Missing local file URI for upload.');
  }
  const file = new ExpoFile(trimmed);
  if (!file.exists) {
    throw new Error('Upload file is missing on device. Try again.');
  }
  // Third arg sets filename under Expo's FormData patch (multipart Content-Disposition).
  form.append(fieldName, file as unknown as Blob, options.name);
}

function sanitizeUploadFilename(name: string): string {
  const base = name.trim().split(/[/\\]/).pop() || 'upload.bin';
  const safe = base.replace(/[^\w.\-()+ ]+/g, '_').slice(0, 180);
  return safe || 'upload.bin';
}

/**
 * Image/video/document pickers can return asset-library or content URIs that
 * expo/fetch cannot stream. Copy those into cache and return a readable file URI.
 */
export async function prepareUploadUri(uri: string, filename: string): Promise<string> {
  const trimmed = uri.trim();
  if (!trimmed) {
    throw new Error('Missing local file URI for upload.');
  }

  const direct = new ExpoFile(trimmed);
  if (direct.exists) {
    return trimmed;
  }

  try {
    const info = await getInfoAsync(trimmed);
    if (info.exists && !info.isDirectory) {
      const readable = new ExpoFile(trimmed);
      if (readable.exists) {
        return trimmed;
      }
    }
  } catch {
    // Fall through to cache copy.
  }

  const dest = new ExpoFile(Paths.cache, `cm_upload_${Date.now()}_${sanitizeUploadFilename(filename)}`);
  await copyAsync({ from: trimmed, to: dest.uri });
  if (!dest.exists) {
    throw new Error('Upload file is missing on device. Try again.');
  }
  return dest.uri;
}
