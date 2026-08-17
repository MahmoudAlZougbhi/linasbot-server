import assert from 'node:assert/strict';
import test from 'node:test';

import {
  conversationHasUserTurn,
  dropUnstartedHistoryEntry,
  listedHistoryEntries,
  mergeListedHistory,
  upsertStartedHistoryEntry,
} from '../src/features/chat/chatHistoryVisibility.ts';

test('listedHistoryEntries omits threads with has_user_message false', () => {
  const listed = listedHistoryEntries([
    { id: 'empty', title: 'New chat', has_user_message: false },
    { id: 'started', title: 'Hello', has_user_message: true, archived: false },
  ]);
  assert.deepEqual(listed, [{ id: 'started', title: 'Hello', archived: false }]);
});

test('conversationHasUserTurn ignores greeting-only transcripts', () => {
  assert.equal(conversationHasUserTurn([{ role: 'assistant', content: 'Hi' }]), false);
  assert.equal(
    conversationHasUserTurn([
      { role: 'assistant' },
      { role: 'user' },
    ]),
    true,
  );
});

test('upsertStartedHistoryEntry inserts then updates title', () => {
  const first = upsertStartedHistoryEntry([], { id: 'c1', title: 'New chat' });
  assert.equal(first.length, 1);
  const next = upsertStartedHistoryEntry(first, { id: 'c1', title: 'Hello there' });
  assert.equal(next.length, 1);
  assert.equal(next[0].title, 'Hello there');
});

test('dropUnstartedHistoryEntry removes chat after failed first send', () => {
  const prev = [{ id: 'c1', title: 'Hello' }, { id: 'c2', title: 'Keep' }];
  const dropped = dropUnstartedHistoryEntry(prev, 'c1', [{ role: 'assistant' }]);
  assert.deepEqual(
    dropped.map((h) => h.id),
    ['c2'],
  );
  const kept = dropUnstartedHistoryEntry(prev, 'c1', [{ role: 'user' }]);
  assert.equal(kept.length, 2);
});

test('mergeListedHistory keeps a better local title over a default list title', () => {
  const prev = [
    { id: 'a', title: 'Pricing help' },
    { id: 'b', title: 'Hours question' },
  ];
  const next = [
    { id: 'a', title: 'New chat' },
    { id: 'b', title: 'Hours question' },
    { id: 'c', title: 'Fresh thread' },
  ];
  const merged = mergeListedHistory(prev, next);
  assert.deepEqual(
    merged.map((h) => h.title),
    ['Pricing help', 'Hours question', 'Fresh thread'],
  );
});

test('mergeListedHistory still accepts a real server title change', () => {
  const prev = [{ id: 'a', title: 'Old name' }];
  const next = [{ id: 'a', title: 'Renamed on server' }];
  assert.equal(mergeListedHistory(prev, next)[0].title, 'Renamed on server');
});
