import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { isPlanId, PLAN_CATALOG } from '../billing/planCatalog';
import type { WebChatSettings } from './webChatApi';

const EntitlementWebSchema = z
  .object({
    success: z.boolean(),
    entitlement: z
      .object({
        plan_id: z.string().optional(),
        subscription_exempt: z.boolean().optional(),
        web: z.boolean().optional(),
        features: z
          .object({
            web: z.boolean().optional(),
          })
          .passthrough()
          .optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();

/** Backend entitlements/me — used when web-chat payload omits membership_allows. */
export async function fetchWebChannelEntitledFromEntitlements(): Promise<boolean | null> {
  try {
    const data = await apiFetch('/api/entitlements/me', { schema: EntitlementWebSchema });
    const ent = data.entitlement;
    if (!ent) return null;
    if (ent.subscription_exempt === true) return true;
    if (ent.web === true) return true;
    if (ent.features?.web === true) return true;
    const planId = (ent.plan_id || '').trim().toLowerCase();
    if (isPlanId(planId) && PLAN_CATALOG[planId].web) return true;
    if (ent.web === false || ent.features?.web === false) return false;
    if (isPlanId(planId) && !PLAN_CATALOG[planId].web) return false;
    return null;
  } catch {
    return null;
  }
}

/** Single source for Integrations Website card gating (API flag + entitlements fallback). */
export function resolveWebPlanAllowed(
  settings: WebChatSettings | null,
  entitlementFallback: boolean | null,
): boolean {
  // Either source granting access wins (handles stale membership_allows on older servers).
  if (entitlementFallback === true || settings?.membership_allows === true) return true;
  if (entitlementFallback === false || settings?.membership_allows === false) return false;
  return false;
}
