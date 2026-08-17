/**
 * Live Chat inbox list merge — poll must not wipe load-more pages.
 * Run: node --test mobile/linas-ai/tests/liveChatInbox.merge.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import {
  appendInboxPage,
  mergeInboxPollPage,
} from '../src/features/livechat/inboxListMerge.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (...p) => readFileSync(join(root, 'src', ...p), 'utf8');

function row(id, name) {
  return { conversation_id: id, user_id: id, user_name: name };
}

test('mergeInboxPollPage keeps load-more rows and updates page-1 titles', () => {
  const prev = [row('1', 'Old A'), row('2', 'B'), row('3', 'C-from-page2')];
  const page1 = [row('9', 'Brand new'), row('1', 'A updated'), row('2', 'B')];
  const merged = mergeInboxPollPage(prev, page1);
  assert.deepEqual(
    merged.map((c) => c.conversation_id),
    ['9', '1', '2', '3'],
  );
  assert.equal(merged.find((c) => c.conversation_id === '1')?.user_name, 'A updated');
  assert.equal(merged.find((c) => c.conversation_id === '3')?.user_name, 'C-from-page2');
});

test('appendInboxPage dedupes by conversation_id', () => {
  const prev = [row('1', 'A')];
  const next = appendInboxPage(prev, [row('1', 'A2'), row('2', 'B')]);
  assert.deepEqual(
    next.map((c) => c.conversation_id),
    ['1', '2'],
  );
  assert.equal(next[0].user_name, 'A');
});

test('inbox hook ignores stale responses and preserves cursor after poll', () => {
  const hook = read('features/livechat/useLiveChatInbox.ts');
  assert.match(hook, /requestIdRef/);
  assert.match(hook, /paginatedBeyondFirstRef/);
  assert.match(hook, /mergeInboxPollPage/);
  assert.match(hook, /appendInboxPage/);
  assert.match(hook, /nextCursorRef/);
  assert.match(hook, /if \(requestId !== requestIdRef\.current\) return/);
});

test('drawer history refresh ignores out-of-order list responses', () => {
  const history = read('features/nav/useModuleDrawerHistory.ts');
  assert.match(history, /requestIdRef/);
  assert.match(history, /mergeListedHistory/);
  assert.match(history, /if \(requestId !== requestIdRef\.current\) return/);
  assert.doesNotMatch(history, /inFlight/);
});
