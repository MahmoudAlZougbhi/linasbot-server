import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

test('Smart Follow-Up screen matches redesign structure', () => {
  const screen = read('features/smartFollowUp/SmartFollowUpScreen.tsx');
  assert.match(screen, /SmartFollowUpChannelsCard/);
  assert.match(screen, /SmartFollowUpStepsCard/);
  assert.match(screen, /sfuEnabledLabel/);
  assert.match(screen, /sfuSaveChanges/);
  assert.match(screen, /sfuWindowCompliance/);
  assert.match(screen, /channels_enabled/);
  assert.doesNotMatch(screen, /SmartFollowUpStepEditor/);
  assert.doesNotMatch(screen, /sfuPreview/);
});

test('Smart Follow-Up channels grid includes supported platforms', () => {
  const opts = read('features/smartFollowUp/smartFollowUpOptions.ts');
  assert.match(opts, /instagram_dm/);
  assert.match(opts, /facebook_messenger/);
  assert.match(opts, /whatsapp_cloud/);
  assert.match(opts, /supported: false/);
});

test('Smart Follow-Up API persists channels_enabled', () => {
  const api = read('features/smartFollowUp/smartFollowUpApi.ts');
  assert.match(api, /channels_enabled/);
});
