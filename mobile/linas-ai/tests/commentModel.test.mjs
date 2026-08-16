/**
 * Comment rule helpers — reply mapping, post ids, resource constraints.
 * Run: node --import ./tests/resolveTsSibling.mjs --experimental-strip-types --test tests/commentModel.test.mjs
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  allowedResourceKinds,
  applyPostsMode,
  applyReplyIn,
  applyReplyType,
  applySelectedPosts,
  createCommentRule,
  filterAttachmentsForReplyIn,
  matchesCommentQuery,
  parseCommentRule,
  parseKeywords,
  replyInOf,
  replyTypeOf,
  ruleToRecord,
  uniquePostIds,
} from '../src/features/cm/comments/commentModel.ts';

test('parseCommentRule unions post_id and post_ids', () => {
  const item = parseCommentRule({
    id: 'r1',
    name: 'Price questions',
    post_id: 'POST_A',
    post_ids: ['POST_B'],
    rule_mode: 'deterministic',
    action: 'reply_comment_and_dm_static',
    keywords: ['price'],
  });
  assert.deepEqual(uniquePostIds(item), ['POST_B', 'POST_A']);
  assert.equal(item.scope, 'specific_post');
  assert.equal(matchesCommentQuery(item, 'price'), true);
  assert.equal(matchesCommentQuery(item, 'laser'), false);
});

test('automatic vs AI reply maps trigger and action', () => {
  let item = createCommentRule('r2');
  item = applyReplyIn(item, 'both');
  item = applyReplyType(item, 'automatic');
  item.reply_template = 'Sent you the details';
  const auto = ruleToRecord(item);
  assert.equal(auto.rule_mode, 'deterministic');
  assert.equal(auto.action, 'reply_comment_and_dm_static');
  assert.equal(auto.trigger_type, 'contains_any');

  item = applyReplyType(item, 'ai');
  item.ai_instructions = 'Answer product questions';
  const ai = ruleToRecord(item);
  assert.equal(ai.rule_mode, 'ai_guidance');
  assert.equal(ai.action, 'reply_comment_and_dm');
  assert.equal(ai.trigger_type, 'all_comments');
  assert.equal(replyTypeOf(parseCommentRule(ai)), 'ai');
});

test('public comment resources are image/link only', () => {
  assert.deepEqual(allowedResourceKinds('comment'), ['image', 'link']);
  assert.deepEqual(allowedResourceKinds('dm'), ['image', 'video', 'file', 'link']);
  const kept = filterAttachmentsForReplyIn(
    [
      { id: '1', kind: 'image', caption: '', mime: '', filename: 'a.jpg', size: 1, url: '', duration_seconds: null },
      { id: '2', kind: 'video', caption: '', mime: '', filename: 'b.mp4', size: 1, url: '', duration_seconds: 18 },
    ],
    'comment',
  );
  assert.equal(kept.length, 1);
  assert.equal(kept[0].kind, 'image');
  assert.equal(replyInOf(applyReplyIn(createCommentRule('r3'), 'dm')), 'dm');
});

test('choose posts persists ids and all posts clears them', () => {
  let item = applySelectedPosts(createCommentRule('r4'), ['p1', 'p2'], { permalink: 'https://ig.me/p', caption: 'Summer' });
  assert.deepEqual(item.post_ids, ['p1', 'p2']);
  assert.equal(item.post_id, 'p1');
  item = applyPostsMode(item, 'all');
  assert.deepEqual(item.post_ids, []);
  assert.equal(item.scope, 'all_posts');
  assert.deepEqual(parseKeywords('price, سعر, قدّي'), ['price', 'سعر', 'قدّي']);
});
