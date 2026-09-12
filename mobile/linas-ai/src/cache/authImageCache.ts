const MAX_ENTRIES = 16;
const MAX_CHARS = 180_000;

const uris = new Map<string, string>();

export function peekAuthImageUri(mediaId: string): string | null {
  const hit = uris.get(mediaId);
  if (!hit) return null;
  uris.delete(mediaId);
  uris.set(mediaId, hit);
  return hit;
}

export function rememberAuthImageUri(mediaId: string, dataUri: string): void {
  if (!mediaId || dataUri.length > MAX_CHARS) return;
  uris.delete(mediaId);
  uris.set(mediaId, dataUri);
  while (uris.size > MAX_ENTRIES) {
    const oldest = uris.keys().next().value;
    if (oldest === undefined) break;
    uris.delete(oldest);
  }
}

export function authImageCacheSize(): number {
  return uris.size;
}

export function clearAuthImageCache(): void {
  uris.clear();
}
