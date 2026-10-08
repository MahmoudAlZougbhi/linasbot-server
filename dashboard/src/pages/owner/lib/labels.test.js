import { describe, expect, it } from 'vitest';
import { MAPS, humanize, label } from './labels';

describe('owner label maps', () => {
  it('covers every map and never returns a raw key', () => {
    for (const [kind, map] of Object.entries(MAPS)) {
      for (const key of Object.keys(map)) {
        expect(label(kind, key)).not.toMatch(/_/);
      }
    }
  });

  it('humanizes unknown keys and keeps brand casing', () => {
    expect(humanize('some_new_key')).toBe('Some new key');
    expect(humanize('ai_dm')).toBe('AI DM');
    expect(label('channel', 'whatsapp')).toBe('WhatsApp');
    expect(label('provider', 'voyage')).toBe('Voyage AI');
  });
});
