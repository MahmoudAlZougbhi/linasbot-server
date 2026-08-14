/**
 * Runtime parse: unlabeled rows stay on All; mixed channels survive one bad row.
 * Run: node --experimental-strip-types --test tests/liveChatInbox.parse.test.mjs
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  UnifiedChatsSchema,
  chatChannel,
  matchesChannelFilter,
  parseLiveChatItems,
  parseUnifiedChatsResponse,
} from '../src/features/livechat/liveChatTypes.ts';

const waIgFb = [
  { conversation_id: 'wa-1', user_id: '+96170111111', user_name: 'Ali' },
  {
    conversation_id: 'ig-1',
    user_id: 'numeric-psid',
    user_name: 'Sara',
    customer_info: { channel: 'instagram_dm' },
  },
  { conversation_id: 'fb-1', user_id: 'facebook:55', user_name: 'Omar' },
];

test('parse keeps rows without channel and mixed WA/IG/FB on All', () => {
  const parsed = UnifiedChatsSchema.parse({
    chats: [
      ...waIgFb,
      { user_name: 'no-ids' },
      { conversation_id: 'tt-1', user_id: 'tiktok:ready', channel: 'tiktok' },
    ],
  });
  const ids = parsed.chats.map((c) => c.conversation_id);
  assert.deepEqual(ids, ['wa-1', 'ig-1', 'fb-1', 'tt-1']);
  assert.equal(
    parsed.chats.filter((c) => matchesChannelFilter(c, 'all')).length,
    4,
  );
  assert.equal(chatChannel(parsed.chats[0]), 'whatsapp');
  assert.equal(chatChannel(parsed.chats[1]), 'instagram');
  assert.equal(chatChannel(parsed.chats[2]), 'facebook');
  assert.equal(chatChannel(parsed.chats[3]), 'tiktok');
  assert.equal(matchesChannelFilter(parsed.chats[0], 'instagram'), false);
  assert.equal(matchesChannelFilter(parsed.chats[1], 'instagram'), true);
});

test('parseLiveChatItems does not require channel', () => {
  const rows = parseLiveChatItems([
    { conversation_id: '1', user_id: 'u1', unread_count: '2', is_new_customer: 1 },
  ]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].conversation_id, '1');
  assert.equal(matchesChannelFilter(rows[0], 'all'), true);
});

test('missing chats key does not throw; missing user_id keeps the row', () => {
  const parsed = UnifiedChatsSchema.parse({ success: true });
  assert.deepEqual(parsed.chats, []);
  const rows = parseLiveChatItems([{ conversation_id: 'wa-orphan', user_id: null, user_name: 'Lina' }]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].user_id, 'wa-orphan');
});

test('parseUnifiedChatsResponse keeps WA/IG/FB when envelope is messy', () => {
  const parsed = parseUnifiedChatsResponse({
    success: false,
    chats: waIgFb,
    source: 'index_error',
  });
  assert.equal(parsed.chats.length, 3);
  assert.equal(
    parsed.chats.filter((c) => matchesChannelFilter(c, 'all')).length,
    3,
  );
  const loose = parseUnifiedChatsResponse({ chats: waIgFb });
  assert.equal(loose.chats.length, 3);
});

test('production-shaped rows with null user_id still render on All', () => {
  const parsed = parseUnifiedChatsResponse({
    success: true,
    counters: { all: 3 },
    chats: [
      {
        conversation_id: 'wa-prod',
        user_id: null,
        phone_number: '+96170123456',
        last_message: { content: 'hello', timestamp: '2026-08-14T12:00:00Z', is_user: true },
        human_takeover_active: null,
      },
      {
        conversation_id: 'ig-prod',
        user_id: null,
        customer_info: { channel: 'instagram_dm' },
        phone_clean: 'instagram:178414000',
        last_message_text: 'hi',
      },
      {
        conversation_id: 'fb-prod',
        user_id: 'facebook:55',
        channel: 'messenger',
      },
    ],
  });
  assert.equal(parsed.chats.length, 3);
  assert.equal(parsed.chats[0].user_id, '+96170123456');
  assert.equal(chatChannel(parsed.chats[0]), 'whatsapp');
  assert.equal(chatChannel(parsed.chats[1]), 'instagram');
  assert.equal(chatChannel(parsed.chats[2]), 'facebook');
  assert.equal(parsed.chats.filter((c) => matchesChannelFilter(c, 'all')).length, 3);
});
