/**
 * Comment inbox SSE merge — inbound appears without refresh; AI reply patches the same row.
 * Run: node --experimental-strip-types --test tests/liveChatComments.sse.test.mjs
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyCommentGridEvent,
  applyCommentThreadEvent,
} from '../src/features/livechat/comments/commentsSseMerge.ts';

const post = {
  id: 'media1',
  caption: 'hello',
  created_time: '',
  permalink: '',
  thumbnail: '',
  media_type: 'IMAGE',
  kind: 'post',
  comment_count: 2,
  watched: true,
};

test('grid bumps count for inbound on the matching post only', () => {
  const next = applyCommentGridEvent(
    [post, { ...post, id: 'media2', comment_count: 0 }],
    { platform: 'instagram', post_id: 'media1', comment_id: 'c1', comment: 'price?' },
    'instagram',
  );
  assert.equal(next[0].comment_count, 3);
  assert.equal(next[1].comment_count, 0);
});

test('thread inserts inbound then attaches AI reply without a second bubble', () => {
  const inbound = applyCommentThreadEvent(
    [],
    { platform: 'instagram', post_id: 'media1', comment_id: 'c1', author: 'Sara', comment: 'price?' },
    'media1',
    'instagram',
  );
  assert.equal(inbound.length, 1);
  assert.equal(inbound[0].comment, 'price?');
  assert.equal(inbound[0].ai_reply, '');
  const withAi = applyCommentThreadEvent(
    inbound,
    { platform: 'instagram', post_id: 'media1', comment_id: 'c1', ai_reply: 'DM us', delivery_status: 'sent' },
    'media1',
    'instagram',
  );
  assert.equal(withAi.length, 1);
  assert.equal(withAi[0].ai_reply, 'DM us');
  assert.equal(withAi[0].delivery_status, 'sent');
});

test('facebook events do not mutate an instagram thread', () => {
  const items = applyCommentThreadEvent(
    [{ comment_id: 'c1', author: 'Sara', comment: 'hi', ai_reply: '', created_at: '', delivery_status: 'none' }],
    { platform: 'facebook', post_id: 'media1', comment_id: 'c1', comment: 'nope' },
    'media1',
    'instagram',
  );
  assert.equal(items[0].comment, 'hi');
});
