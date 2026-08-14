/**
 * New-chat welcome is a server-seeded hardcoded pool, not a live LLM greeting.
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const mobileRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = join(mobileRoot, '..', '..');

function readMobile(rel) {
  return readFileSync(join(mobileRoot, 'src', ...rel.split('/')), 'utf8');
}

test('new owner chat seeds greeting from server picker, not a local LLM', () => {
  const session = readMobile('features/chat/useChatSession.ts');
  assert.match(session, /\/api\/owner-ai\/conversations/);
  assert.match(session, /method: 'POST'/);
  assert.match(session, /seedTypewriterMessageId/);
  assert.doesNotMatch(session, /openai|generateWelcome|chat\.completions/i);
});

test('owner greeting module uses hardcoded pool, not stage-status copy', () => {
  const greeting = readFileSync(join(repoRoot, 'services/owner_ai_greeting.py'), 'utf8');
  assert.match(greeting, /pick_welcome/);
  assert.doesNotMatch(greeting, /core looks configured/i);
  assert.doesNotMatch(greeting, /AI Setup tweaks/);
  assert.doesNotMatch(greeting, /Everything core/);
  const en = readFileSync(join(repoRoot, 'services/welcome_pool/en.py'), 'utf8');
  const ar = readFileSync(join(repoRoot, 'services/welcome_pool/ar.py'), 'utf8');
  const fr = readFileSync(join(repoRoot, 'services/welcome_pool/fr.py'), 'utf8');
  assert.match(en, /Welcome back — what do you want to do today/);
  assert.doesNotMatch(en, /core looks configured|AI Setup|System Copilot/i);
  assert.doesNotMatch(ar, /الإعداد الأساسي يبدو مكتملاً/);
  assert.doesNotMatch(fr, /L’essentiel semble configuré/);
});
