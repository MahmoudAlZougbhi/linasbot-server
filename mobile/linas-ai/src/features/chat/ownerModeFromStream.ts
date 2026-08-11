import type { OwnerChatMode } from './ownerChatMode';

/** Upgrade chip to Work/High when the stream reports high Sol effort (never auto-downgrade). */
export function ownerModeFromStreamRoute(
  current: OwnerChatMode,
  route: unknown,
): OwnerChatMode {
  if (!route || typeof route !== 'object') return current;
  const r = route as Record<string, unknown>;
  const suggested = r.suggested_owner_mode;
  if (suggested === 'work') return 'work';
  if (r.reasoning_effort === 'high') return 'work';
  return current;
}

/** CM / write tools mid-turn → show High immediately (sticky until user picks Low). */
const CM_STATUS_TOOLS =
  /^(propose_cm_|approve_cm_|publish_cm|validate_cm|read_cm|list_cm|inspect_cm|cm_fill_plan|ingest_business_dump)/i;

export function ownerModeFromStreamStatus(
  current: OwnerChatMode,
  statusId: string | null | undefined,
): OwnerChatMode {
  const id = (statusId || '').trim();
  if (!id) return current;
  if (CM_STATUS_TOOLS.test(id)) return 'work';
  return current;
}
