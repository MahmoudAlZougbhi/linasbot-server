/**
 * Integrations list + 3-dot sheet design (no device required).
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);
const read = (...p) => readFileSync(src(...p), 'utf8');

test('list chrome matches Integrations handoff', () => {
  const screen = read('features/integrations/IntegrationsScreen.tsx');
  const shell = read('features/integrations/IntegrationCardShell.tsx');
  const en = read('i18n/locales/en.ts');
  const display = read('i18n/locales/integrationsDisplayEn.ts');
  assert.match(screen, /IntegrationRefreshButton/);
  assert.match(screen, /tr\('integrationsSub'\)/);
  assert.match(en, /Connect and manage your channels/);
  assert.match(shell, /borderRadius:\s*14/);
  assert.match(shell, /shadowOpacity/);
  assert.doesNotMatch(shell, /card: \{[^}]*borderWidth/);
  assert.match(shell, /colors\.accentSoft/);
  assert.match(display, /Business number/);
});

test('connected cards use 3-dot menu, Messages/Comments toggles, and healthy footer', () => {
  const card = read('features/integrations/IntegrationChannelCard.tsx');
  const shell = read('features/integrations/IntegrationCardShell.tsx');
  const toggles = read('features/integrations/ChannelCapabilityToggles.tsx');
  const display = read('i18n/locales/integrationsDisplayEn.ts');
  assert.match(shell, /more-horizontal/);
  assert.match(card, /showMenu=\{!soon && row\.connected\}/);
  assert.match(card, /integrationToggleMessages/);
  assert.match(card, /toggleComments/);
  assert.match(card, /integrationStatusConnected/);
  assert.match(toggles, /trackColor=\{\s*\{\s*false:\s*'#D5DBDB',\s*true:\s*colors\.accent/);
  assert.doesNotMatch(toggles, /integrationConnectedFeatures/);
  assert.doesNotMatch(toggles, /integrationFeatureOn/);
  assert.match(display, /integrationToggleMessages: 'Messages'/);
  assert.match(display, /Connection healthy/);
});

test('disconnected WhatsApp shows outlined Connect and no toggles', () => {
  const wa = read('features/integrations/WhatsAppCloudCard.tsx');
  const shell = read('features/integrations/IntegrationCardShell.tsx');
  assert.match(wa, /showConnect=\{!connected && connectable\}/);
  assert.match(wa, /showComments=\{false\}/);
  assert.match(wa, /integrationWhatsAppHandle/);
  assert.match(shell, /connectBtn/);
  assert.match(shell, /borderColor:\s*colors\.accent/);
});

test('3-dot sheet has refresh, disconnect, disclaimer, cancel — no Meta reconnect', () => {
  const sheet = read('features/integrations/IntegrationAccountSheet.tsx');
  const screen = read('features/integrations/IntegrationsScreen.tsx');
  const display = read('i18n/locales/integrationsDisplayEn.ts');
  assert.match(sheet, /styles\.handle/);
  assert.match(sheet, /feather\('x'\)/);
  assert.match(sheet, /feather\('refresh-cw'\)/);
  assert.match(sheet, /feather\('log-out'\)/);
  assert.match(sheet, /colors\.danger/);
  assert.match(sheet, /disconnectHint/);
  assert.match(sheet, /styles\.cancel/);
  assert.match(display, /Refresh status/);
  assert.match(display, /Disconnect account/);
  assert.match(display, /AI replies stop until you reconnect/);
  assert.doesNotMatch(sheet, /manageMetaAccess/);
  assert.doesNotMatch(sheet, /integrationReconnect/);
  assert.doesNotMatch(sheet, /reconnectWithCommentAccess/);
  assert.doesNotMatch(screen, /manageMetaAccess/);
  assert.doesNotMatch(screen, /Reconnect/);
});

test('TikTok card is shown from product list without faking a connection', () => {
  const screen = read('features/integrations/IntegrationsScreen.tsx');
  assert.match(screen, /platform === 'tiktok'/);
  assert.match(screen, /tiktokRow/);
  assert.match(screen, /soon=\{isComingSoon\(tiktokRow\)\}/);
  assert.doesNotMatch(screen, /connected:\s*true.*tiktok/);
});
