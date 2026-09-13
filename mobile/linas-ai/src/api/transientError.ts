/** Deploy drain, nginx 502, timeout, or a dropped connection — not a billing denial. */

function errorStatus(err: unknown): number | null {
  if (!err || typeof err !== 'object') return null;
  if (!('status' in err)) return null;
  const status = (err as { status: unknown }).status;
  return typeof status === 'number' ? status : null;
}

export function isTransientServiceError(err: unknown): boolean {
  const status = errorStatus(err);
  if (status != null) {
    if (status === 401 || status === 402 || status === 403) return false;
    return status >= 500 || status === 408;
  }
  return true;
}
