/**
 * Live Chat inbox design + operator actions (no device required).
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

test('inbox is a flat list with All/Human filters and no section headers', () => {
  const hook = read('features/livechat/useLiveChatInbox.ts');
  const inbox = read('features/livechat/LiveChatInbox.tsx');
  assert.doesNotMatch(hook, /Waiting for human|With operator|AI handling/);
  assert.doesNotMatch(inbox, /section\.title|kind === 'header'/);
  assert.match(inbox, /InboxSearchBar/);
  assert.match(inbox, /InboxChannelChips/);
  assert.match(inbox, /InboxFilterPills/);
  assert.match(inbox, /<FlatList/);
  assert.match(inbox, /data=\{visibleChats\}/);
  assert.match(inbox, /styles\.toolbar/);
  assert.match(inbox, /styles\.listWrap/);
  assert.doesNotMatch(inbox, /if \(loading\) \{/);
  const chips = read('features/livechat/InboxChannelChips.tsx');
  assert.match(chips, /flexGrow:\s*0/);
  assert.match(chips, /height:\s*CHIP_ROW_H/);
  assert.match(inbox, /minHeight:\s*0/);
  assert.match(inbox, /ConversationRow/);
  assert.match(chips, /reqFilterAll/);
  assert.match(chips, /styles\.allLabel/);
  assert.match(chips, /chip\.id === 'all'/);
  assert.match(chips, /PlatformChannelIcon/);
});

test('row layout is icon / name+preview / time+badge+assignee', () => {
  const row = read('features/livechat/ConversationRow.tsx');
  assert.match(row, /styles\.middle/);
  assert.match(row, /styles\.meta/);
  assert.match(row, /badgeSpacer/);
  assert.match(row, /assigneeLabel\(item\)/);
  assert.match(row, /chatChannel\(item\)/);
  assert.doesNotMatch(row, /chatAvatarLetter/);
});

test('thread restores WhatsApp handoff, assign, and composer', () => {
  const thread = read('features/livechat/LiveChatThread.tsx');
  const composer = read('features/livechat/LiveChatComposer.tsx');
  const api = read('features/livechat/liveChatApi.ts');
  const hook = read('features/livechat/useLiveChatThread.ts');
  assert.match(thread, /LiveChatComposer/);
  assert.match(thread, /onSendMedia/);
  assert.match(composer, /onSendMedia/);
  assert.match(composer, /feather\('image'\)/);
  assert.match(composer, /feather\('mic'\)/);
  assert.match(thread, /LiveChatAssignSheet/);
  assert.match(thread, /thread\.takeover\(staff\.id\)/);
  assert.match(api, /assignToUserId/);
  assert.match(hook, /takeoverConversation\(chat!, assignToUserId\)/);
  assert.match(hook, /dispatchOperatorSend/);
  assert.doesNotMatch(hook, /sendText:[\s\S]*setBusy\(true\)/);
  assert.doesNotMatch(hook, /WhatsApp-only for now/);
});
