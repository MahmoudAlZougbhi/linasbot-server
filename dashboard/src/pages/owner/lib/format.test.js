import { describe, expect, it } from 'vitest';
import { businessDisplayName, formatDateTime, formatNumber, formatRelative, formatUsd } from './format';

describe('owner format', () => {
  it('formats Cairo time from an ISO timestamp', () => {
    expect(formatDateTime('2026-10-08T08:22:32Z')).toBe('Oct 8, 2026, 11:22 AM');
  });

  it('formats numbers and dollars', () => {
    expect(formatNumber(24990)).toBe('24,990');
    expect(formatNumber(null)).toBe('—');
    expect(formatUsd(259)).toBe('$259');
    expect(formatUsd(59.5)).toBe('$59.50');
    expect(formatUsd(0.0042)).toBe('$0.0042');
    expect(formatUsd('0')).toBe('$0');
  });

  it('uses relative time only for the last day', () => {
    const now = Date.parse('2026-10-08T12:00:00Z');
    expect(formatRelative(now - 30_000, now)).toBe('just now');
    expect(formatRelative(now - 59 * 60_000, now)).toBe('59 min ago');
    expect(formatRelative(now - 23 * 60 * 60_000, now)).toBe('23 h ago');
    expect(formatRelative(now - 25 * 60 * 60_000, now)).toBe(formatDateTime(now - 25 * 60 * 60_000));
    expect(formatRelative(now - 8 * 24 * 60 * 60_000, now)).toBe(formatDateTime(now - 8 * 24 * 60 * 60_000));
  });

  it('prefers a business name over an email', () => {
    expect(businessDisplayName({ business_name: 'Linas', tenant_id: 'linas', email: 'a@b.com' })).toBe('Linas');
    expect(businessDisplayName({ business_name: 'a@b.com', tenant_id: 'chance-app' })).toBe('Chance App');
    expect(businessDisplayName({ email: 'only@example.com' })).toBe('only@example.com');
  });
});
