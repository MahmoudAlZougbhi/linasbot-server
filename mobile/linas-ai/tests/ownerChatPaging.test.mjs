import assert from 'node:assert/strict';
import test from 'node:test';

import {
  mergeLatestWindow,
  messagesIncludeAssistantReply,
} from '../src/features/chat/ownerChatPaging.ts';

test('mergeLatestWindow keeps streamed turn after server catches up', () => {
  const greeting = { id: 'g1', role: 'assistant', content: 'Hi', created_at: 1 };
  const userLocal = { id: 'local-1', role: 'user', content: 'Hello', created_at: 2 };
  const user = { id: 'u1', role: 'user', content: 'Hello', created_at: 2 };
  const assistant = { id: 'a1', role: 'assistant', content: 'Reply here', created_at: 3 };
  const merged = mergeLatestWindow([greeting, userLocal], [greeting, user, assistant]);
  assert.equal(merged.length, 3);
  assert.ok(messagesIncludeAssistantReply(merged, 'Reply here'));
});

test('messagesIncludeAssistantReply matches assistant prefix', () => {
  const msgs = [{ id: 'a1', role: 'assistant', content: 'Long assistant answer', created_at: 1 }];
  assert.equal(messagesIncludeAssistantReply(msgs, 'Long assistant'), true);
  assert.equal(messagesIncludeAssistantReply(msgs, 'missing'), false);
});

test('mergeLatestWindow keeps a Sol reply the server page omitted', () => {
  const greeting = { id: 'g1', role: 'assistant', content: 'Hi', created_at: 1 };
  const user = { id: 'u1', role: 'user', content: 'Hello', created_at: 2 };
  const sol = { id: 'a1', role: 'assistant', content: 'Here is the answer', created_at: 3 };
  const merged = mergeLatestWindow([greeting, user, sol], [greeting, user]);
  assert.equal(merged.map((m) => m.id).join(','), 'g1,u1,a1');
});

test('messagesIncludeAssistantReply ignores an older Sol bubble', () => {
  const msgs = [
    { id: 'a1', role: 'assistant', content: 'Long assistant answer', created_at: 1 },
    { id: 'u1', role: 'user', content: 'next', created_at: 2 },
    { id: 'a2', role: 'assistant', content: 'Different reply', created_at: 3 },
  ];
  assert.equal(messagesIncludeAssistantReply(msgs, 'Long assistant'), false);
  assert.equal(messagesIncludeAssistantReply(msgs, 'Different reply'), true);
});
