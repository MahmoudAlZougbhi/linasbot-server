/**
 * Regression: server iap_note:null must not fail Zod and fail-close the gate.
 * Run: node --test tests/subscriptionAccessNullNote.test.mjs
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { z } from 'zod';

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
        iap_note: z.string().nullable().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();

function allowedFrom(ent) {
  return (
    ent.app_access === true ||
    ent.subscription_exempt === true ||
    (typeof ent.app_access !== 'boolean' &&
      ['active', 'trial', 'grace'].includes(String(ent.status || '')) &&
      Boolean(ent.plan_id && ent.plan_id !== 'none'))
  );
}

describe('subscription entitlements schema', () => {
  it('parses linas exempt payload when iap_note is JSON null', () => {
    const parsed = EntitlementMeSchema.parse({
      success: true,
      entitlement: {
        tenant_id: 'linas',
        plan_id: 'none',
        status: 'none',
        app_access: true,
        subscription_exempt: true,
        subscription_required: false,
        iap_purchase_in_app: false,
        iap_note: null,
        price_usd: null,
        current_period_end: null,
      },
    });
    assert.equal(allowedFrom(parsed.entitlement), true);
  });

  it('parses payload when iap_note key is omitted', () => {
    const parsed = EntitlementMeSchema.parse({
      success: true,
      entitlement: {
        tenant_id: 'linas',
        plan_id: 'none',
        status: 'none',
        app_access: true,
        subscription_exempt: true,
        iap_purchase_in_app: false,
      },
    });
    assert.equal(allowedFrom(parsed.entitlement), true);
  });

  it('still denies non-exempt unpaid tenants', () => {
    const parsed = EntitlementMeSchema.parse({
      success: true,
      entitlement: {
        tenant_id: 'proof-clinic',
        plan_id: 'none',
        status: 'none',
        app_access: false,
        subscription_exempt: false,
        iap_note: null,
      },
    });
    assert.equal(allowedFrom(parsed.entitlement), false);
  });
});
