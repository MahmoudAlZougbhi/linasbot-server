/** Keep OAuth/action feedback separate from transient integrations-list loading. */
export function errorAfterIntegrationLoadSuccess(
  current: string | null,
  loadError: string,
): string | null {
  return current === loadError ? null : current;
}

export function errorAfterIntegrationLoadFailure(
  current: string | null,
  loadError: string,
): string {
  return current || loadError;
}

/** A deep-link result received during the browser session owns the final feedback. */
export function shouldApplyMetaSessionFeedback(
  deepLinkSequenceAtStart: number,
  currentDeepLinkSequence: number,
): boolean {
  return deepLinkSequenceAtStart === currentDeepLinkSequence;
}
