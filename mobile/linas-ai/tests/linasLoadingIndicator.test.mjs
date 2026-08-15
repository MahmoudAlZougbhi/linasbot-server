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

test('screen loaders use LinasLoadingIndicator on key surfaces', () => {
  const integrations = read('features/integrations/IntegrationsScreen.tsx');
  const users = read('features/users/UsersScreen.tsx');
  const dashboard = read('features/dashboard/DashboardScreen.tsx');
  assert.match(integrations, /LinasLoadingIndicator/);
  assert.match(integrations, /showInitialLoader/);
  assert.match(users, /LinasLoadingIndicator/);
  assert.doesNotMatch(users, /ActivityIndicator/);
  assert.match(dashboard, /LinasLoadingIndicator/);
  assert.doesNotMatch(dashboard, /ActivityIndicator/);
});
