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
