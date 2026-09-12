/**
 * Opening a bot Live Chat thread must not pause AI (Assign to AI must stick).
 * Run: node --import ./tests/resolveTsSibling.mjs --experimental-strip-types --test tests/liveChatClaimOnOpen.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('Live Chat assign-to-AI stays on AI while viewing', () => {
  it('claimOnOpen only marks read and never takeovers', () => {
    const src = read('features/livechat/useLiveChatThread.ts');
    const start = src.indexOf('const claimOnOpen');
    const end = src.indexOf('return {', start);
    assert.ok(start >= 0 && end > start);
    const claim = src.slice(start, end);
    assert.match(claim, /markConversationRead/);
    assert.doesNotMatch(claim, /takeoverConversation/);
    assert.doesNotMatch(claim, /status !== 'bot'/);
  });

  it('thread chrome can leave to inbox so heartbeat stops', () => {
    const src = read('features/livechat/LiveChatScreen.tsx');
    assert.match(src, /if \(selected\)[\s\S]*onBack=\{\(\) => setSelected\(null\)\}/);
  });
});
