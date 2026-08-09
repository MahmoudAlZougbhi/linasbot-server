import { File as ExpoFile } from 'expo-file-system';

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
