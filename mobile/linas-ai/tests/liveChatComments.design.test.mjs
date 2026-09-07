/**
 * Live Chat Comments grid — Instagram-style posts, platform chips, thread.
 * Run: node --test mobile/linas-ai/tests/liveChatComments.design.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);
const read = (...p) => readFileSync(src(...p), 'utf8');

test('Live Chat has Chats / Comments switch and comment grid', () => {
  const screen = read('features/livechat/LiveChatScreen.tsx');
  const inbox = read('features/livechat/comments/CommentsInbox.tsx');
  const grid = read('features/livechat/comments/CommentsMediaGrid.tsx');
  const chips = read('features/livechat/comments/CommentsPlatformChips.tsx');
  assert.match(screen, /LiveChatSurfaceSwitch/);
  assert.match(screen, /CommentsInbox/);
  assert.match(screen, /CommentThreadScreen/);
  assert.match(inbox, /CommentsPlatformChips/);
  assert.match(inbox, /CommentsMediaGrid/);
  assert.match(inbox, /CommentPostSheet/);
  assert.match(grid, /numColumns=\{3\}/);
  assert.match(grid, /comment_count/);
  assert.match(chips, /id: 'instagram'/);
  assert.match(chips, /id: 'facebook'/);
  assert.match(chips, /id: 'tiktok'/);
  assert.doesNotMatch(chips, /whatsapp/);
});

test('post sheet shows caption, kind, view, and watch toggle', () => {
  const sheet = read('features/livechat/comments/CommentPostSheet.tsx');
  const thread = read('features/livechat/comments/CommentThreadScreen.tsx');
  assert.match(sheet, /liveCommentsView/);
  assert.match(sheet, /liveCommentsOpenThread/);
  assert.match(sheet, /liveCommentsReplyOn/);
  assert.match(sheet, /caption/);
  assert.match(thread, /liveCommentsAiReply/);
  assert.match(thread, /item.comment/);
  assert.match(thread, /item.ai_reply/);
});
