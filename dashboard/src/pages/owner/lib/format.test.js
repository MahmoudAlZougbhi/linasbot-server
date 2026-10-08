import { describe, expect, it } from 'vitest';
import { formatDateTime, formatNumber, formatUsd } from './format';

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
});
