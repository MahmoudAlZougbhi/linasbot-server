/**
 * True only for transport / device-offline failures — not HTTP 4xx/5xx or app errors.
 * Used so chat never labels auth/API/stream server errors as "offline".
 */
export function isNetworkFailure(err: unknown): boolean {
  if (err == null) return false;
  if (err instanceof TypeError) return true;

  const msg = String(
    typeof err === 'object' && err !== null && 'message' in err
      ? (err as { message?: unknown }).message
      : err,
  ).toLowerCase();

  return (
    msg === 'stream_network_error' ||
    msg.includes('network request failed') ||
    msg.includes('failed to fetch') ||
    msg.includes('network error') ||
    msg.includes('the internet connection appears to be offline') ||
    msg.includes('nsurlerrordomain')
  );
}
