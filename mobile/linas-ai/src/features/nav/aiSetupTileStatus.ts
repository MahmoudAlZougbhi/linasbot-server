export type AiSetupTileStatus = 'continue' | 'complete' | 'needs_attention';

/**
 * Featured AI Setup drawer badge.
 * - complete + published → Setup Complete
 * - incomplete with published → Needs Attention (partial publish)
 * - incomplete / not published → Continue Setup
 * - fetch error → Needs Attention
 */
export function resolveAiSetupTileStatus(opts: {
  fetchFailed: boolean;
  incomplete: number;
  published: boolean;
}): AiSetupTileStatus {
  if (opts.fetchFailed) return 'needs_attention';
  if (opts.incomplete <= 0 && opts.published) return 'complete';
  if (opts.incomplete > 0 && opts.published) return 'needs_attention';
  return 'continue';
}
