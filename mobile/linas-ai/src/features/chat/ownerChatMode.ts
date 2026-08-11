import { detectCmWorkIntent } from './detectCmWorkIntent';

/** Owner Chat|Work mode — maps to gpt-5.6-sol effort (display: 5.6 LIN). */
export type OwnerChatMode = 'chat' | 'work';

export const OWNER_LIN_DISPLAY = '5.6 LIN';

export function effortLabelForMode(mode: OwnerChatMode): 'Low' | 'High' {
  return mode === 'work' ? 'High' : 'Low';
}

export function modelChipLabel(mode: OwnerChatMode): string {
  return `${OWNER_LIN_DISPLAY} ${effortLabelForMode(mode)}`;
}

/**
 * CM-related owner text auto-upgrades to Work/High for this turn.
 * Chip stays High until the owner manually picks Low (no auto-downgrade).
 */
export function resolveOwnerModeForOutgoing(
  current: OwnerChatMode,
  text: string | null | undefined,
): OwnerChatMode {
  if (current === 'work') return 'work';
  if (detectCmWorkIntent(text)) return 'work';
  return current;
}
