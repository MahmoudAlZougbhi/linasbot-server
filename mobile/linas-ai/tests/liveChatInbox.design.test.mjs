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
  assert.match(inbox, /InboxFilterPills/);
  assert.match(inbox, /data=\{chats\}/);
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
  const api = read('features/livechat/liveChatApi.ts');
  const hook = read('features/livechat/useLiveChatThread.ts');
  assert.match(thread, /LiveChatComposer/);
  assert.match(thread, /LiveChatAssignSheet/);
  assert.match(thread, /thread\.takeover\(staff\.id\)/);
  assert.match(api, /assignToUserId/);
  assert.match(hook, /takeoverConversation\(chat!, assignToUserId\)/);
  assert.match(hook, /Operator mutations are not allowed for Instagram\/Facebook/);
});
