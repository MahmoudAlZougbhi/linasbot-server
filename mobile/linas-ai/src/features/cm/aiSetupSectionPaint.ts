export type AiSetupSectionPaint = 'pending' | 'missing' | 'complete';

/**
 * Section tile chrome. Unknown fill is pending — never "missing" before load.
 */
export function resolveAiSetupSectionPaint(
  fill: 'complete' | 'incomplete' | undefined,
): AiSetupSectionPaint {
  if (fill === 'incomplete') return 'missing';
  if (fill === 'complete') return 'complete';
  return 'pending';
}
