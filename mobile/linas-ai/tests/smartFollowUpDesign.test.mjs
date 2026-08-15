import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

test('Smart Follow-Up layout: no Enabled, business hours first, no extra copy', () => {
  const screen = read('features/smartFollowUp/SmartFollowUpScreen.tsx');
  assert.match(screen, /SmartFollowUpChannelsCard/);
  assert.match(screen, /SmartFollowUpStepsCard/);
  assert.match(screen, /sfuSaveChanges/);
  assert.match(screen, /channels_enabled/);
  assert.match(screen, /featureEnabledFromSteps/);
  assert.match(screen, /enabled:\s*featureEnabledFromSteps\(steps\)/);
  assert.doesNotMatch(screen, /sfuEnabledLabel/);
  assert.doesNotMatch(screen, /sfuAiWritesBody/);
  assert.doesNotMatch(screen, /sfuWindowCompliance/);
  assert.doesNotMatch(screen, /sparkles/);
  assert.doesNotMatch(screen, /shield-checkmark/);
  assert.doesNotMatch(screen, /SmartFollowUpStepEditor/);
  assert.doesNotMatch(screen, /sfuPreview/);
  assert.doesNotMatch(screen, /stackedHeader/);
  const hours = screen.indexOf("tr('sfuBusinessHours')");
  const channels = screen.indexOf('<SmartFollowUpChannelsCard');
  const steps = screen.indexOf('<SmartFollowUpStepsCard');
  assert.ok(hours !== -1 && channels !== -1 && steps !== -1);
  assert.ok(hours < channels, 'Business hours only must sit above Channels');
  assert.ok(channels < steps, 'Channels must sit above Follow-up steps');
});

test('Smart Follow-Up header shares a row with the silver hamburger', () => {
  const screen = read('features/smartFollowUp/SmartFollowUpScreen.tsx');
  const chrome = read('features/shared/ScreenChrome.tsx');
  const icons = read('features/chat/ChatHeaderIcons.tsx');
  assert.match(screen, /title=\{tr\('sfuTitle'\)\}/);
  assert.match(screen, /subtitle=\{tr\('sfuSubtitle'\)\}/);
  assert.doesNotMatch(screen, /stackedHeader/);
  assert.match(chrome, /HeaderMenuButton/);
  assert.match(chrome, /headerRowTitleTop/);
  assert.match(chrome, /titleBlockWithSub/);
  assert.match(chrome, /alignItems:\s*'flex-start'/);
  assert.match(icons, /featuredIconBg/);
  assert.match(icons, /HEADER_ICON_BOX = 36/);
});

test('Follow-up steps card matches screenshot structure', () => {
  const steps = read('features/smartFollowUp/SmartFollowUpStepsCard.tsx');
  const dropdown = read('features/smartFollowUp/SmartFollowUpDropdown.tsx');
  const en = read('i18n/locales/smartFollowUpEn.ts');
  assert.match(steps, /sfuStepsTitle/);
  assert.match(en, /sfuStepsTitle:\s*'Follow-up steps'/);
  assert.match(steps, /fonts\.display/);
  assert.match(steps, /SFU_STEP_RADIUS/);
  assert.match(steps, /styles\.hairline/);
  assert.match(steps, /StyleSheet\.hairlineWidth/);
  assert.match(steps, /width:\s*28/);
  assert.match(steps, /trackColor=\{\{ false: colors\.border, true: SFU_TEAL \}\}/);
  assert.doesNotMatch(steps, /formatDelayOptionLabel/);
  assert.doesNotMatch(steps, /sfuAiWritesBody/);
  assert.match(dropdown, /chevron-down/);
  assert.match(dropdown, /flex = 1/);
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

test('removed Follow-Up copy is gone from locales', () => {
  const en = read('i18n/locales/smartFollowUpEn.ts');
  const ar = read('i18n/locales/smartFollowUpAr.ts');
  const fr = read('i18n/locales/smartFollowUpFr.ts');
  for (const loc of [en, ar, fr]) {
    assert.doesNotMatch(loc, /sfuEnabledLabel/);
    assert.doesNotMatch(loc, /sfuAiWritesBody/);
    assert.doesNotMatch(loc, /sfuWindowCompliance/);
    assert.match(loc, /sfuStepsTitle/);
  }
});
