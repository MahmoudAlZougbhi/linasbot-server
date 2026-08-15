/**
 * Linas branded loading indicator — design contract (no device required).
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (rel) => readFileSync(join(root, 'src', rel), 'utf8');

test('LinasLoadingIndicator uses sparkle mark with breathe animation', () => {
  const loader = read('components/LinasLoadingIndicator.tsx');
  const hook = read('hooks/useReduceMotion.ts');
  assert.match(loader, /LinasStarMark/);
  assert.match(loader, /useReduceMotion/);
  assert.match(loader, /Animated\.loop/);
  assert.match(loader, /variant === 'screen'/);
  assert.match(loader, /accessibilityRole="progressbar"/);
  assert.doesNotMatch(loader, /<ActivityIndicator/);
  assert.match(hook, /isReduceMotionEnabled/);
});

test('useScreenLoadGate exposes initial-load vs refresh semantics', () => {
  const gate = read('hooks/useScreenLoadGate.ts');
  assert.match(gate, /showInitialLoader/);
  assert.match(gate, /hasLoadedOnce/);
  assert.match(gate, /isRefreshing/);
});

const SCREEN_SURFACES = [
  'features/integrations/IntegrationsScreen.tsx',
  'features/users/UsersScreen.tsx',
  'features/dashboard/DashboardScreen.tsx',
  'features/faq/FaqScreen.tsx',
  'features/products/ProductsScreen.tsx',
  'features/notifications/NotificationsScreen.tsx',
  'features/requests/RequestsHome.tsx',
  'features/livechat/LiveChatInbox.tsx',
  'features/livechat/LiveChatThread.tsx',
  'features/cm/CmScreen.tsx',
  'features/cm/CmSectionScreen.tsx',
  'features/smartFollowUp/SmartFollowUpScreen.tsx',
  'features/billing/BillingScreen.tsx',
  'features/integrations/WebsiteIntegrationScreen.tsx',
  'features/chat/ChatScreen.tsx',
  'features/control/OwnerPortalScreen.tsx',
  'features/products/AddProductScreen.tsx',
];

test('screen loaders use LinasLoadingIndicator on feature surfaces', () => {
  for (const rel of SCREEN_SURFACES) {
    const source = read(rel);
    assert.match(source, /LinasLoadingIndicator/, `${rel} should import LinasLoadingIndicator`);
    assert.match(source, /variant="screen"/, `${rel} should use screen variant for initial load`);
    assert.doesNotMatch(source, /<ActivityIndicator/, `${rel} should not use ActivityIndicator`);
  }
});

test('integrations gates content until first load and web chat are ready', () => {
  const integrations = read('features/integrations/IntegrationsScreen.tsx');
  assert.match(integrations, /showInitialLoader/);
  assert.match(integrations, /hasLoadedOnce/);
  assert.match(integrations, /webChatReady/);
  assert.match(integrations, /headerRefreshing/);
});

test('dashboard hides content until ready state', () => {
  const dashboard = read('features/dashboard/DashboardScreen.tsx');
  assert.match(dashboard, /state\.kind === 'loading' \? <LinasLoadingIndicator variant="screen" \/> : null/);
  assert.match(dashboard, /state\.kind === 'ready' \? \([\s\S]*<DashboardHeader/);
});
