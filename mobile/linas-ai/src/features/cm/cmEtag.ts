/**
 * CM draft ETags are stored as quoted HTTP tags, e.g. `"3-ab12cd34ef56ab78"`.
 * Use the JSON body etag as the If-Match value. Never strip quotes from the
 * header — that makes a successful writer look like a concurrent conflict.
 */
export function resolveCmEtag(
  bodyEtag: unknown,
  headerEtag: string | null | undefined,
  fallback = '',
): string {
  if (typeof bodyEtag === 'string' && bodyEtag.trim()) return bodyEtag.trim();
  if (typeof headerEtag === 'string' && headerEtag.trim()) return headerEtag.trim();
  return fallback;
}
