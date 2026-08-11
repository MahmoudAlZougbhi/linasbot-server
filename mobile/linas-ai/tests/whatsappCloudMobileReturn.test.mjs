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
    assert.match(screen, /startWhatsAppCloudConnect/);
    assert.match(screen, /wa_connection|waConnection|waOAuthSuccess/);
  });

  it('WhatsApp card never asks for pasted tokens', () => {
    const card = read('features/integrations/WhatsAppCloudCard.tsx');
    assert.match(card, /startWhatsAppCloudConnect/);
    assert.doesNotMatch(card, /paste.*(token|waba|phone)/i);
  });
});
