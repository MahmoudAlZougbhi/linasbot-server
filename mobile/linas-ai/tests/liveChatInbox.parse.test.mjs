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
} from '../src/features/livechat/liveChatTypes.ts';

test('parse keeps rows without channel and mixed WA/IG/FB on All', () => {
  const parsed = UnifiedChatsSchema.parse({
    chats: [
      { conversation_id: 'wa-1', user_id: '+96170111111', user_name: 'Ali' },
      {
        conversation_id: 'ig-1',
        user_id: 'numeric-psid',
        user_name: 'Sara',
        customer_info: { channel: 'instagram_dm' },
      },
      { conversation_id: 'fb-1', user_id: 'facebook:55', user_name: 'Omar' },
      { conversation_id: 'bad', user_id: null },
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
