/**
 * Screen loaders: sparkle stays for inline work; first paint uses ScreenSkeleton.
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
  assert.match(gate, /ScreenSkeleton/);
});

const SHELL_SURFACES = [
  'features/integrations/IntegrationsScreen.tsx',
  'features/users/UsersScreen.tsx',
  'features/dashboard/DashboardScreen.tsx',
  'features/faq/FaqScreen.tsx',
  'features/products/ProductsScreen.tsx',
  'features/notifications/NotificationsScreen.tsx',
  'features/requests/RequestsHome.tsx',
  'features/livechat/LiveChatInbox.tsx',
  'features/cm/CmScreen.tsx',
  'features/cm/CmSectionScreen.tsx',
  'features/smartFollowUp/SmartFollowUpScreen.tsx',
  'features/billing/BillingScreen.tsx',
  'features/integrations/WebsiteIntegrationScreen.tsx',
  'features/control/OwnerPortalScreen.tsx',
  'features/products/AddProductScreen.tsx',
  'features/services/ServicesScreen.tsx',
];

test('module first paint uses ScreenSkeleton, not full-screen sparkle', () => {
  for (const rel of SHELL_SURFACES) {
    const source = read(rel);
    assert.match(source, /ScreenSkeleton/, `${rel} should use ScreenSkeleton`);
    assert.doesNotMatch(source, /variant="screen"/, `${rel} must not wait behind a screen spinner`);
    assert.doesNotMatch(source, /<ActivityIndicator/, `${rel} should not use ActivityIndicator`);
  }
});

test('integrations gates content until first load; web chat can arrive after', () => {
  const integrations = read('features/integrations/IntegrationsScreen.tsx');
  assert.match(integrations, /showInitialLoader/);
  assert.match(integrations, /hasLoadedOnce/);
  assert.match(integrations, /webChatReady/);
  assert.match(integrations, /headerRefreshing/);
  assert.match(integrations, /showInitialLoader = !hasLoadedOnce/);
  assert.match(integrations, /ScreenSkeleton variant="cards"/);
  assert.doesNotMatch(integrations, /showInitialLoader = !hasLoadedOnce \|\| !webChatReady/);
});

test('Owner Copilot chat never uses a full-screen loader', () => {
  const chat = read('features/chat/ChatScreen.tsx');
  assert.doesNotMatch(chat, /LinasLoadingIndicator/);
  assert.doesNotMatch(chat, /<ActivityIndicator/);
  assert.match(chat, /ChatMessageList/);
});

test('dashboard keeps header visible and uses chart skeleton while loading', () => {
  const dashboard = read('features/dashboard/DashboardScreen.tsx');
  assert.match(dashboard, /<DashboardHeader/);
  assert.match(dashboard, /state\.kind === 'loading' \|\| state\.kind === 'ready'/);
  assert.match(dashboard, /state\.kind === 'loading' \? <ScreenSkeleton variant="chart" \/> : null/);
});
