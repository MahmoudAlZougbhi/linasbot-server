/**
 * Locations & hours helpers — clock format, today status, search, media count.
 * Run: node --import ./tests/resolveTsSibling.mjs --experimental-strip-types --test tests/locationHours.test.mjs
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  applyScheduleToDays,
  branchAddress,
  branchMediaCount,
  formatClock12,
  hoursAreSet,
  matchesBranchQuery,
  parseClock12,
  todayStatus,
} from '../src/features/cm/editors/locationOpeningHours/branchScheduleHelpers.ts';
import { emptyWeeklySchedule } from '../src/features/cm/editors/locationOpeningHours/branchScheduleTypes.ts';

describe('clock 12h roundtrip', () => {
  it('formats and parses AM/PM times used on the hours screen', () => {
    assert.equal(formatClock12('09:00'), '9:00 AM');
    assert.equal(formatClock12('20:00'), '8:00 PM');
    assert.equal(parseClock12('9:00 AM'), '09:00');
    assert.equal(parseClock12('8:00 PM'), '20:00');
    assert.equal(parseClock12('10:00'), '10:00');
  });
});

describe('today status and draft', () => {
  it('treats empty weekly schedule as no hours / draft', () => {
    const empty = emptyWeeklySchedule();
    assert.equal(hoursAreSet(empty), false);
    assert.equal(todayStatus(empty).kind, 'none');
  });

  it('reports open or closed from the weekday row', () => {
    const schedule = emptyWeeklySchedule();
    const monday = new Date('2026-08-17T12:00:00');
    schedule.monday = { enabled: true, open: '09:00', close: '20:00', off_day: false, note: null };
    assert.equal(todayStatus(schedule, monday).kind, 'open');
    schedule.monday.off_day = true;
    schedule.monday.open = '';
    schedule.monday.close = '';
    assert.equal(todayStatus(schedule, monday).kind, 'closed');
  });

  it('applies one schedule to selected days', () => {
    const next = applyScheduleToDays(emptyWeeklySchedule(), ['monday', 'tuesday'], {
      enabled: true,
      off_day: false,
      open: '10:00',
      close: '17:00',
      note: null,
    });
    assert.equal(next.monday.open, '10:00');
    assert.equal(next.tuesday.close, '17:00');
    assert.equal(next.wednesday.enabled, false);
  });
});

describe('list search and media count', () => {
  it('matches name or address and counts maps + attachments', () => {
    const branch = {
      labels: { en: 'Beirut — Ramlet El Bayda' },
      address: 'Abdul Aziz St, Beirut',
      maps_url: 'https://maps.google.com/x',
      attachments: [{ id: 'a' }, { id: 'b' }],
    };
    assert.equal(matchesBranchQuery(branch, 'ramlet'), true);
    assert.equal(matchesBranchQuery(branch, 'aziz'), true);
    assert.equal(matchesBranchQuery(branch, 'tripoli'), false);
    assert.equal(branchMediaCount(branch), 3);
  });

  it('keeps trailing spaces in the typed address field', () => {
    assert.equal(branchAddress({ address: 'Abdul Aziz St ' }), 'Abdul Aziz St ');
  });
});
