/** Owner Chat|Work mode — maps to gpt-5.6-sol effort (display: 5.6 LIN). */
export type OwnerChatMode = 'chat' | 'work';

export const OWNER_LIN_DISPLAY = '5.6 LIN';

export function effortLabelForMode(mode: OwnerChatMode): 'Low' | 'High' {
  return mode === 'work' ? 'High' : 'Low';
}

export function modelChipLabel(mode: OwnerChatMode): string {
  return `${OWNER_LIN_DISPLAY} ${effortLabelForMode(mode)}`;
}
