import { z } from 'zod';

import { apiFetch } from '../../api/client';

const EntitlementMeSchema = z
  .object({
    success: z.boolean(),
    entitlement: z
      .object({
        plan_id: z.string().optional(),
        status: z.string().optional(),
        app_access: z.boolean().optional(),
        subscription_exempt: z.boolean().optional(),
        iap_purchase_in_app: z.boolean().optional(),
        iap_note: z.string().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();

export type SubscriptionAccess = {
  allowed: boolean;
  planId: string | null;
  status: string | null;
  iapPurchaseInApp: boolean;
  note: string | null;
};

/** Real entitlement check — backend `app_access` is source of truth (includes exempt tenants). */
export async function fetchSubscriptionAccess(): Promise<SubscriptionAccess> {
  const data = await apiFetch('/api/entitlements/me', { schema: EntitlementMeSchema });
  const ent = data.entitlement;
  if (!ent) {
    return { allowed: false, planId: null, status: null, iapPurchaseInApp: false, note: null };
  }
  const allowed =
    ent.app_access === true ||
    ent.subscription_exempt === true ||
    (typeof ent.app_access !== 'boolean' &&
      ['active', 'trial', 'grace'].includes(String(ent.status || '')) &&
      Boolean(ent.plan_id && ent.plan_id !== 'none'));
  return {
    allowed,
    planId: ent.plan_id ?? null,
    status: ent.status ?? null,
    iapPurchaseInApp: Boolean(ent.iap_purchase_in_app),
    // Never surface server engineering notes (iap_note) in production UI.
    note: null,
  };
}
