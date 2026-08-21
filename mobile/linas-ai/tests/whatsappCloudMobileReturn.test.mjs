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
    const link = read('app/integrationsDeepLink.ts');
    assert.match(link, /wa_connection/);
    assert.match(link, /waConnection/);
    assert.doesNotMatch(link, /access_token/);
  });

  it('Integrations deep link ignores bridge subpaths', () => {
    const link = read('app/integrationsDeepLink.ts');
    assert.match(link, /path !== 'integrations'/);
    assert.match(link, /never bridge URLs/);
  });

  it('IntegrationsScreen wires WhatsApp card and deep-link refetch', () => {
    const screen = read('features/integrations/IntegrationsScreen.tsx');
    const load = read('features/integrations/useIntegrationsLoad.ts');
    assert.match(screen, /WhatsAppCloudCard/);
    assert.match(screen, /useWhatsAppIntegrations/);
    assert.match(load, /wa_connection|waConnection|waOAuthSuccess/);
  });

  it('WhatsApp card never asks for pasted tokens', () => {
    const card = read('features/integrations/WhatsAppCloudCard.tsx');
    assert.match(card, /startWhatsAppCloudConnect|fetchWhatsAppCloudStatus/);
    assert.match(card, /waStateAwaitingMetaApproval|awaitingMeta/);
    assert.doesNotMatch(card, /paste.*(token|waba|phone)/i);
  });

  it('Connect uses expo-web-browser auth session, not dynamic Linking import', () => {
    const connect = read('features/integrations/whatsappCloudConnect.ts');
    assert.match(connect, /expo-web-browser/);
    assert.match(connect, /openAuthSessionAsync/);
    assert.match(connect, /connectInFlight|connect_in_progress/);
    assert.doesNotMatch(connect, /await import\(['"]react-native['"]\)/);
    assert.doesNotMatch(connect, /Linking\.openURL/);
    assert.match(connect, /WhatsAppConnectError/);
  });

  it('hook guards double-tap and maps recoverable connect errors', () => {
    const hook = read('features/integrations/useWhatsAppIntegrations.ts');
    assert.match(hook, /if \(waBusy\) return/);
    assert.match(hook, /WhatsAppConnectError/);
    assert.match(hook, /waOAuthCancelled/);
    assert.match(hook, /waConnectBrowserUnavailable|waConnectConfigMissing/);
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

  it('Meta Connect uses an in-app auth session; TikTok keeps Linking; WA stays separate', () => {
    const oauth = read('features/integrations/integrationsOAuth.ts');
    assert.match(oauth, /openAuthSessionAsync/);
    assert.match(oauth, /startTikTokOAuth[\s\S]*Linking\.openURL/);
    assert.doesNotMatch(oauth, /whatsappCloudConnect/);
  });
});
