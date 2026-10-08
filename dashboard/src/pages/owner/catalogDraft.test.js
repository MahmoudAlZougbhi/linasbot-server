import { describe, expect, it } from 'vitest';
import { freeDraftFromCatalog, planDraftFromCatalog } from './catalogDraft';

describe('catalog drafts', () => {
  it('round trips plan and free drafts', () => {
    const catalog = {
      plans: [{ plan_id: 'max', intended_price_usd: 279, included_messages: 25000, faq_capacity: 40 }],
      free: { included_messages: 20, configured: { free_message_renewal: 'monthly' } },
    };
    expect(planDraftFromCatalog(catalog).max.included_messages).toBe(25000);
    expect(freeDraftFromCatalog(catalog).configured.free_message_renewal).toBe('monthly');
  });
});
