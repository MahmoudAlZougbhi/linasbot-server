import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  isWhatsAppAppReviewTest,
  normalizeWhatsAppRecipient,
  whatsappApiErrorDetail,
  whatsappConnectionSubtitle,
} from '../src/features/integrations/whatsappCloudPresentation.ts';

describe('WhatsApp connected-number presentation', () => {
  it('shows the full connected business number with the verified name', () => {
    assert.equal(
      whatsappConnectionSubtitle(
        {
          verified_name: 'Test Number',
          display_phone_number: '+1 555 673 4285',
          display_phone_last4: '4285',
        },
        'WhatsApp Business',
      ),
      'Test Number · +1 555 673 4285',
    );
  });

  it('falls back safely when the full number is absent', () => {
    assert.equal(
      whatsappConnectionSubtitle({ verified_name: 'Clinic', display_phone_last4: '2722' }, 'WhatsApp'),
      'Clinic · ••••2722',
    );
  });

  it('identifies the fixed App Review source', () => {
    assert.equal(isWhatsAppAppReviewTest({ connection_source: 'meta_app_review_test' }), true);
    assert.equal(isWhatsAppAppReviewTest({ connection_source: 'embedded_signup' }), false);
  });

  it('normalizes international recipients and rejects local or empty values', () => {
    assert.equal(normalizeWhatsAppRecipient('+961 3 956 607'), '9613956607');
    assert.equal(normalizeWhatsAppRecipient('+1 (555) 673-4285'), '15556734285');
    assert.equal(normalizeWhatsAppRecipient('03956607'), null);
    assert.equal(normalizeWhatsAppRecipient(''), null);
  });

  it('rejects letters and garbage instead of silently changing the recipient', () => {
    assert.equal(normalizeWhatsAppRecipient('+1555O6734285'), null);
    assert.equal(normalizeWhatsAppRecipient('call +1 555 673 4285'), null);
    assert.equal(normalizeWhatsAppRecipient('1555.673.4285'), null);
    assert.equal(normalizeWhatsAppRecipient('1555+6734285'), null);
    assert.equal(normalizeWhatsAppRecipient('++15556734285'), null);
  });

  it('surfaces a safe API response detail', () => {
    assert.equal(whatsappApiErrorDetail({ body: { detail: 'to_wa_id_required' } }), 'to_wa_id_required');
    assert.equal(whatsappApiErrorDetail(new Error('Request failed')), null);
  });
});
