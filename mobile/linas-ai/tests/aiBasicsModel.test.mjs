/**
 * AI Basics greeting model — parse, note sync, search, attachments.
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  emptyGreeting,
  greetingToRecord,
  matchesGreetingQuery,
  parseGreeting,
  parseGreetings,
  withGreetingNote,
} from '../src/features/cm/aiBasics/aiBasicsModel.ts';

describe('aiBasicsModel', () => {
  it('parses greeting notes with en fallback and attachments', () => {
    const item = parseGreeting({
      id: 'g1',
      enabled: true,
      name: 'Default welcome',
      en: 'Hello there',
      attachments: [
        {
          id: 'a1',
          kind: 'image',
          title: 'Smile',
          description: 'Welcome image',
          filename: 'smile-welcome.jpg',
        },
      ],
    });
    assert.equal(item.notes, 'Hello there');
    assert.equal(item.attachments[0].filename, 'smile-welcome.jpg');
    assert.equal(item.attachments[0].title, 'Smile');
  });

  it('keeps note + en in sync and serializes attachments', () => {
    const base = emptyGreeting();
    const next = withGreetingNote(base, 'Welcome every new customer warmly.');
    assert.equal(next.notes, 'Welcome every new customer warmly.');
    assert.equal(next.en, 'Welcome every new customer warmly.');
    const dumped = greetingToRecord({
      ...next,
      name: 'Default welcome',
      attachments: [
        {
          id: 'a1',
          kind: 'file',
          title: 'Guide',
          description: 'PDF welcome',
          caption: 'PDF welcome',
          mime: 'application/pdf',
          filename: 'welcome-guide.pdf',
          size: 1200000,
          url: '',
          duration_seconds: null,
        },
      ],
    });
    assert.equal(dumped.name, 'Default welcome');
    assert.equal(dumped.notes, 'Welcome every new customer warmly.');
    assert.ok(Array.isArray(dumped.attachments));
    assert.equal(dumped.attachments[0].filename, 'welcome-guide.pdf');
  });

  it('filters greetings by title or note', () => {
    const items = parseGreetings({
      items: [
        { id: '1', name: 'Default welcome', notes: 'Warm hello' },
        { id: '2', name: 'New customer details', notes: 'Ask for name' },
      ],
    });
    assert.equal(items.filter((row) => matchesGreetingQuery(row, 'welcome')).length, 1);
    assert.equal(items.filter((row) => matchesGreetingQuery(row, 'ask')).length, 1);
    assert.equal(items.filter((row) => matchesGreetingQuery(row, '')).length, 2);
  });
});
