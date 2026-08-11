import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('whatsapp cloud mobile return + card', () => {
  it('parses wa_connection deep link without tokens', () => {
    const nav = read('app/navigation.ts');
    assert.match(nav, /wa_connection/);
    assert.match(nav, /waConnection/);
    assert.doesNotMatch(nav, /access_token/);
  });

  it('IntegrationsScreen wires WhatsApp card and deep-link refetch', () => {
    const screen = read('features/integrations/IntegrationsScreen.tsx');
    assert.match(screen, /WhatsAppCloudCard/);
    assert.match(screen, /useWhatsAppIntegrations/);
    assert.match(screen, /wa_connection|waConnection|waOAuthSuccess/);
  });

  it('WhatsApp card never asks for pasted tokens', () => {
    const card = read('features/integrations/WhatsAppCloudCard.tsx');
    assert.match(card, /startWhatsAppCloudConnect|fetchWhatsAppCloudStatus/);
    assert.match(card, /waStateAwaitingMetaApproval|awaitingMeta/);
    assert.doesNotMatch(card, /paste.*(token|waba|phone)/i);
  });

  it('ops panel exposes App Review surfaces', () => {
    const ops = read('features/integrations/WhatsAppCloudOpsPanel.tsx');
    assert.match(ops, /sendWhatsAppTestMessage/);
    assert.match(ops, /createWhatsAppTemplate/);
    assert.match(ops, /resumeWhatsAppConversation/);
    assert.match(ops, /pauseWhatsAppConversation/);
  });

  it('Owner Portal grants pilot without hardcoded tenant', () => {
    const portal = read('features/control/OwnerPortalScreen.tsx');
    assert.match(portal, /pilot\/grant/);
    assert.match(portal, /tenant_id/);
    assert.doesNotMatch(portal, /tenant_id:\s*['"]linas['"]|@gmail\.com|mahmoud@/i);
  });
});
