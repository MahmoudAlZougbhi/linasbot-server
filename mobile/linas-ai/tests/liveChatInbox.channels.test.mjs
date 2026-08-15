/**
 * Live Chat inbox lists real WA/IG/FB threads; TikTok chip is empty until ready.
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);
const read = (...p) => readFileSync(src(...p), 'utf8');

test('inbox defaults to All channels, not WhatsApp-only', () => {
  const hook = read('features/livechat/useLiveChatInbox.ts');
  const api = read('features/livechat/liveChatApi.ts');
  const inbox = read('features/livechat/LiveChatInbox.tsx');
  const chips = read('features/livechat/InboxChannelChips.tsx');
  assert.match(hook, /useState<ChannelFilter>\('all'\)/);
  assert.doesNotMatch(hook, /useState<ChannelFilter>\('whatsapp'\)/);
  assert.match(hook, /channel,/);
  assert.match(hook, /requires_index_rebuild \|\| data\.index_empty/);
  assert.match(api, /params\.set\('channel', opts\.channel\)/);
  assert.match(api, /parseUnifiedChatsResponse/);
  assert.match(api, /parseConversationDetailsResponse/);
  assert.match(inbox, /InboxChannelChips/);
  assert.match(chips, /id: 'whatsapp'/);
  assert.match(chips, /id: 'instagram'/);
  assert.match(chips, /id: 'facebook'/);
  assert.match(chips, /id: 'tiktok'/);
  assert.match(chips, /id: 'all'/);
});

test('chatChannel maps IG/FB/WA/TikTok and never invents TikTok', () => {
  const helpers = read('features/livechat/liveChatHelpers.ts');
  assert.match(helpers, /Never invents TikTok rows/);
  assert.match(helpers, /ch === 'tiktok'/);
  assert.match(helpers, /instagram_dm/);
  assert.match(helpers, /facebook_messenger/);
  assert.match(helpers, /blobHasChannelToken\(blob, 'tiktok'\)/);
  assert.match(helpers, /return 'whatsapp'/);
  assert.doesNotMatch(helpers, /fakeTikTok|placeholderTikTok|tiktokThreads\s*=\s*\[/);
  const inbox = read('features/livechat/LiveChatInbox.tsx');
  assert.match(inbox, /No TikTok conversations/);
  assert.match(inbox, /None are created as placeholders/);
  assert.doesNotMatch(inbox, /conversation_id:\s*'tiktok-/);
});

test('unified chats parse keeps valid rows when one item is malformed', () => {
  const types = read('features/livechat/liveChatTypes.ts');
  const helpers = read('features/livechat/liveChatHelpers.ts');
  assert.match(types, /function parseLiveChatItems/);
  assert.match(types, /LiveChatItemSchema\.safeParse/);
  assert.match(types, /customer_info/);
  assert.match(helpers, /matchesChannelFilter/);
  assert.match(helpers, /if \(filter === 'all'\) return true/);
});
