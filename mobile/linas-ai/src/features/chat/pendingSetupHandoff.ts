/** In-memory handoff from CM readiness CTA → Owner Copilot chat. */

export type PendingSetupHandoff = {
  text: string;
  mode: 'work';
  autoSend: boolean;
};

let pending: PendingSetupHandoff | null = null;

export function queueSetupHandoff(handoff: PendingSetupHandoff): void {
  const text = handoff.text.trim();
  pending = text ? { ...handoff, text } : null;
}

export function takeSetupHandoff(): PendingSetupHandoff | null {
  const next = pending;
  pending = null;
  return next;
}
