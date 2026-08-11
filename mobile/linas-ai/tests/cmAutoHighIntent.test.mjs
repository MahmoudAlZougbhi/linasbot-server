import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const detectSrc = path.join(root, 'src/features/chat/detectCmWorkIntent.ts');
const modeSrc = path.join(root, 'src/features/chat/ownerChatMode.ts');
const streamSrc = path.join(root, 'src/features/chat/ownerModeFromStream.ts');
const screenSrc = path.join(root, 'src/features/chat/ChatScreen.tsx');
const turnSrc = path.join(root, 'src/features/chat/v2/useStreamingTurn.ts');

/** Mirrors detectCmWorkIntent.ts */
const CM_WORK_INTENT =
  /\b(content\s*management|content\s*manager|content-manager|\bcm\b)\b|\b(faq|smart\s*answers?|knowledge|handoff|publish|draft|validate)\b|\b(opening\s*hours?|business\s*hours?|working\s*hours?|off\s*days?)\b|\b(ai\s*basics|ai\s*limits|dynamic\s*messages|care\s*instructions|response\s*style|ai\s*style)\b|\b(prices?|branches?|services?|languages?|restricted|sections?)\b|(إدارة\s*المحتوى|كونتنت|محتوى)|(\bFAQ\b|أسئلة\s*شائعة|سؤال\s*وجواب)|(ساعات\s*(العمل|الدوام)?|مواعيد\s*(العمل|الدوام)?|دوام)|(معرفة|انشر|نشر|أسعار|فروع|خدمات|أسئلة)/i;

function detectCmWorkIntent(text) {
  const raw = (text || '').trim();
  if (!raw) return false;
  return CM_WORK_INTENT.test(raw);
}

function resolveOwnerModeForOutgoing(current, text) {
  if (current === 'work') return 'work';
  if (detectCmWorkIntent(text)) return 'work';
  return current;
}

function ownerModeFromStreamRoute(current, route) {
  if (!route || typeof route !== 'object') return current;
  if (route.suggested_owner_mode === 'work') return 'work';
  if (route.reasoning_effort === 'high') return 'work';
  return current;
}

test('detectCmWorkIntent catches FAQ / hours / Arabic CM talk', () => {
  assert.equal(detectCmWorkIntent('Ask about our FAQ'), true);
  assert.equal(detectCmWorkIntent('What are opening hours?'), true);
  assert.equal(detectCmWorkIntent('Update knowledge section'), true);
  assert.equal(detectCmWorkIntent('publish the draft'), true);
  assert.equal(detectCmWorkIntent('شو ساعات الدوام؟'), true);
  assert.equal(detectCmWorkIntent('أسئلة شائعة'), true);
  assert.equal(detectCmWorkIntent('How does billing work?'), false);
  assert.equal(detectCmWorkIntent(''), false);
});

test('resolveOwnerModeForOutgoing upgrades chat→work for CM and stays sticky', () => {
  assert.equal(resolveOwnerModeForOutgoing('chat', 'FAQ please'), 'work');
  assert.equal(resolveOwnerModeForOutgoing('work', 'hello'), 'work');
  assert.equal(resolveOwnerModeForOutgoing('chat', 'hello'), 'chat');
});

test('ownerModeFromStreamRoute never auto-downgrades', () => {
  assert.equal(ownerModeFromStreamRoute('chat', { reasoning_effort: 'high' }), 'work');
  assert.equal(ownerModeFromStreamRoute('chat', { suggested_owner_mode: 'work' }), 'work');
  assert.equal(ownerModeFromStreamRoute('work', { reasoning_effort: 'low' }), 'work');
  assert.equal(ownerModeFromStreamRoute('chat', { reasoning_effort: 'low' }), 'chat');
});

test('source wiring keeps CM auto-High + stream chip sync', () => {
  const detect = readFileSync(detectSrc, 'utf8');
  const mode = readFileSync(modeSrc, 'utf8');
  const stream = readFileSync(streamSrc, 'utf8');
  const screen = readFileSync(screenSrc, 'utf8');
  const turn = readFileSync(turnSrc, 'utf8');
  assert.match(detect, /export function detectCmWorkIntent/);
  assert.match(mode, /resolveOwnerModeForOutgoing/);
  assert.match(stream, /suggested_owner_mode/);
  assert.match(screen, /resolveOwnerModeForOutgoing/);
  assert.match(screen, /onOwnerModeHint/);
  assert.match(turn, /onOwnerModeHint/);
  assert.match(turn, /ownerModeFromStreamRoute/);
});
