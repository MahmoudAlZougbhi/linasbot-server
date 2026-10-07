import { describe, expect, it } from 'vitest';
import { PAYMENT_LABELS, READINESS_LABELS, paymentLabel, readinessLabel } from './ownerLabels';

const BLOCKERS = [
  'free_ai_message_allowance',
  'message_catalog_unpublished',
  'live_message_skus_not_sale_ready',
  'alembic_head',
  'eval_suite_below_800',
  'stale_leftover_credit_holds',
];

describe('owner labels', () => {
  it('gives every readiness fixture key a human label', () => {
    for (const key of BLOCKERS) {
      expect(READINESS_LABELS[key]).toBeTruthy();
      expect(readinessLabel(key)).not.toContain('_');
    }
  });

  it('maps the Google billing blocker', () => {
    expect(PAYMENT_LABELS.google_iap_not_fully_implemented).toBeTruthy();
    expect(paymentLabel('google_iap_not_fully_implemented')).not.toContain('_');
    expect(paymentLabel('incomplete')).toBe('Incomplete');
  });
});
