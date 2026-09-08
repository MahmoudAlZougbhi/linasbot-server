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
  assert.match(screen, /useLiveChatAccess/);
  assert.match(screen, /CommentsInbox/);
  assert.match(screen, /CommentThreadScreen/);
  assert.match(inbox, /CommentsPlatformChips/);
  assert.match(inbox, /allowedChannels/);
  assert.match(chips, /allowedCommentPlatforms/);
  assert.match(inbox, /CommentsMediaGrid/);
  assert.match(inbox, /onOpenThread\(platform, post\)/);
  assert.doesNotMatch(inbox, /CommentPostSheet/);
  assert.doesNotMatch(inbox, /liveCommentsAllPosts/);
  assert.doesNotMatch(inbox, /liveCommentsChosenPosts/);
  assert.doesNotMatch(inbox, /onToggleWatch/);
  assert.match(grid, /numColumns=\{COLS\}/);
  assert.match(grid, /marginHorizontal: -spacing\.lg/);
  assert.match(grid, /tileAspect/);
  assert.match(grid, /4 \/ 5/);
  assert.match(grid, /fadeDuration=\{0\}/);
  assert.match(grid, /comment_count/);
  assert.doesNotMatch(grid, /onToggleWatch/);
  assert.match(chips, /id: 'instagram'/);
  assert.match(chips, /id: 'facebook'/);
  assert.match(chips, /id: 'tiktok'/);
  assert.doesNotMatch(chips, /whatsapp/);
});

test('thread shows a large post image above comments and optional Linas reply', () => {
  const thread = read('features/livechat/comments/CommentThreadScreen.tsx');
  assert.match(thread, /post.thumbnail/);
  assert.match(thread, /aspectRatio: tall \? 4 \/ 5 : 1/);
  assert.match(thread, /liveCommentsAiReply/);
  assert.match(thread, /liveCommentsWaitingReply/);
  assert.match(thread, /liveCommentsNoComments/);
  assert.match(thread, /item.comment/);
  assert.match(thread, /item.ai_reply/);
});
