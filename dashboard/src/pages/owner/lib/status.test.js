import { describe, expect, it } from 'vitest';
import { statusLabel, statusTone } from './status';

describe('status tones', () => {
  it('maps message and account states', () => {
    expect(statusTone('message', 'sent')).toBe('success');
    expect(statusLabel('message', 'failed')).toBe('Failed');
    expect(statusTone('message', 'pending_settlement')).toBe('warning');
    expect(statusLabel('user', 'test')).toBe('Test account');
    expect(statusLabel('planLive', false)).toBe('Not live yet');
    expect(statusTone('planLive', false)).toBe('neutral');
  });
});
