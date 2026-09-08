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
import {
  hasPendingOperatorSend,
  mergeThreadMessages,
} from '../src/features/livechat/liveChatThreadMerge.ts';

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

test('poll replaces the optimistic send instead of flashing a second copy', () => {
  const local = {
    message_id: 'local-1',
    timestamp: '2026-09-08T08:07:01.000Z',
    is_user: false,
    content: 'hello',
    text: 'hello',
    role: 'operator',
  };
  const older = {
    message_id: 'msg_old',
    timestamp: '2026-09-08T08:00:00.000Z',
    is_user: true,
    content: 'hi',
  };
  const echo = {
    message_id: 'msg_new',
    timestamp: '2026-09-08T08:07:01.400Z',
    is_user: false,
    content: 'hello',
    text: 'hello',
    role: 'operator',
  };
  const merged = mergeThreadMessages([older, local], [older, echo]);
  assert.deepEqual(
    merged.map((m) => m.message_id),
    ['msg_old', 'msg_new'],
  );
});

test('two identical sends keep two server echoes', () => {
  const first = {
    message_id: 'local-1',
    timestamp: '2026-09-08T08:07:01.000Z',
    is_user: false,
    content: 'ok',
    text: 'ok',
  };
  const second = {
    message_id: 'local-2',
    timestamp: '2026-09-08T08:07:02.000Z',
    is_user: false,
    content: 'ok',
    text: 'ok',
  };
  const echo1 = {
    message_id: 'msg_a',
    timestamp: '2026-09-08T08:07:01.200Z',
    is_user: false,
    content: 'ok',
    text: 'ok',
  };
  const echo2 = {
    message_id: 'msg_b',
    timestamp: '2026-09-08T08:07:02.200Z',
    is_user: false,
    content: 'ok',
    text: 'ok',
  };
  const merged = mergeThreadMessages([first, second], [echo1, echo2]);
  assert.deepEqual(
    merged.map((m) => m.message_id),
    ['msg_a', 'msg_b'],
  );
});

test('in-flight optimistic voice stays until the server echo arrives', () => {
  const local = {
    message_id: 'local-voice',
    timestamp: '2026-09-08T08:07:01.000Z',
    is_user: false,
    content: '[Voice Message from Operator]',
    type: 'voice',
    audio_url: 'data:audio/mp4;base64,aaa',
  };
  const prior = {
    message_id: 'msg_old',
    timestamp: '2026-09-08T08:00:00.000Z',
    is_user: true,
    content: 'hi',
  };
  const pending = mergeThreadMessages([prior, local], [prior]);
  assert.equal(pending.length, 2);
  assert.equal(pending[1].message_id, 'local-voice');

  const echo = {
    message_id: 'msg_voice',
    timestamp: '2026-09-08T08:07:01.300Z',
    is_user: false,
    content: '[Voice Message from Operator]',
    type: 'voice',
    audio_url: 'https://cdn/voice.m4a',
  };
  const acked = mergeThreadMessages(pending, [prior, echo]);
  assert.deepEqual(
    acked.map((m) => m.message_id),
    ['msg_old', 'msg_voice'],
  );
  assert.equal(acked[1].audio_url, 'https://cdn/voice.m4a');
});

test('poll keeps a newer echo and a stable client_send_id across the remount', () => {
  const older = {
    message_id: 'msg_old',
    timestamp: '2026-09-08T08:00:00.000Z',
    is_user: true,
    content: 'hi',
  };
  const local = {
    message_id: 'local-keep',
    client_send_id: 'local-keep',
    timestamp: '2026-09-08T08:07:04.000Z',
    is_user: false,
    content: 'hello',
    text: 'hello',
  };
  const echo = {
    message_id: 'msg_new',
    timestamp: '2026-09-08T08:07:04.200Z',
    is_user: false,
    content: 'hello',
    text: 'hello',
  };
  const acked = mergeThreadMessages([older, local], [older, echo]);
  assert.equal(acked[1].client_send_id, 'local-keep');
  assert.equal(acked[1].client_send_id, local.client_send_id);

  const stale = mergeThreadMessages(acked, [older]);
  assert.deepEqual(
    stale.map((m) => m.message_id),
    ['msg_old', 'msg_new'],
  );
});

test('stale poll that misses an acked send keeps the bubble and client_send_id', () => {
  const older = {
    message_id: 'msg_old',
    timestamp: '2026-09-08T08:00:00.000Z',
    is_user: true,
    content: 'hi',
  };
  const newerCustomer = {
    message_id: 'msg_later',
    timestamp: '2026-09-08T08:07:10.000Z',
    is_user: true,
    content: 'ok',
  };
  const acked = {
    message_id: 'msg_new',
    client_send_id: 'local-keep',
    timestamp: '2026-09-08T08:07:04.200Z',
    is_user: false,
    content: 'hello',
    text: 'hello',
  };
  const stale = mergeThreadMessages([older, acked], [older, newerCustomer]);
  assert.deepEqual(
    stale.map((m) => m.message_id),
    ['msg_old', 'msg_new', 'msg_later'],
  );
  assert.equal(stale[1].client_send_id, 'local-keep');

  const again = mergeThreadMessages(stale, [older, acked, newerCustomer]);
  assert.deepEqual(
    again.map((m) => m.message_id),
    ['msg_old', 'msg_new', 'msg_later'],
  );
  assert.equal(again[1].client_send_id, 'local-keep');
});

test('poll without echo keeps the in-flight optimistic send', () => {
  const older = {
    message_id: 'msg_old',
    timestamp: '2026-09-08T08:00:00.000Z',
    is_user: true,
    content: 'hi',
  };
  const local = {
    message_id: 'local-pending',
    client_send_id: 'local-pending',
    timestamp: '2026-09-08T08:07:04.000Z',
    is_user: false,
    content: 'hello',
    text: 'hello',
  };
  const pending = mergeThreadMessages([older, local], [older]);
  assert.equal(hasPendingOperatorSend(pending), true);
  assert.equal(pending[1].message_id, 'local-pending');
});

test('duplicate webhook rows collapse to one bubble', () => {
  const echo = {
    message_id: 'msg_new',
    timestamp: '2026-09-08T08:07:01.400Z',
    is_user: false,
    content: 'hello',
    text: 'hello',
  };
  const merged = mergeThreadMessages([], [echo, { ...echo }]);
  assert.deepEqual(
    merged.map((m) => m.message_id),
    ['msg_new'],
  );
});

test('thread hook ignores stale polls and locks in-flight sends', () => {
  const hook = read('features/livechat/useLiveChatThread.ts');
  const thread = read('features/livechat/LiveChatThread.tsx');
  assert.match(hook, /requestIdRef/);
  assert.match(hook, /if \(requestId !== requestIdRef\.current\) return/);
  assert.match(hook, /sendingRef/);
  assert.match(hook, /hasPendingOperatorSend/);
  assert.match(hook, /async function dispatchOperatorSend/);
  assert.match(hook, /mode === 'poll' \|\| prev.length/);
  assert.match(hook, /if \(!chat \|\| !payload \|\| sendingRef\.current\) return false/);
  assert.match(thread, /thread\.loading && !thread\.messages\.length/);
});

test('drawer history refresh ignores out-of-order list responses', () => {
  const history = read('features/nav/useModuleDrawerHistory.ts');
  assert.match(history, /requestIdRef/);
  assert.match(history, /mergeListedHistory/);
  assert.match(history, /if \(requestId !== requestIdRef\.current\) return/);
  assert.doesNotMatch(history, /inFlight/);
});
