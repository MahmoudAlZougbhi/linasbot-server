/**
 * Services CM catalog helpers (no device required).
 * Run: node --import ./tests/resolveTsSibling.mjs --experimental-strip-types --test tests/serviceModel.test.mjs
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildPriceEntry,
  createCatalogItem,
  emptyPriceDraft,
  formatDuration,
  formatMoney,
  formatPriceFooter,
  matchesServiceQuery,
  parseAmount,
  parseDurationMinutes,
  parseServices,
  patchCatalogItem,
  slugDimension,
} from '../src/features/services/serviceModel.ts';

test('parseServices maps catalog + entries into list cards', () => {
  const items = parseServices({
    catalog: [
      {
        id: 'svc_1',
        labels: { en: 'Laser hair removal', ar: '', fr: '', franco: '' },
        description: 'Full treatment details and aftercare',
        attachments: [{ id: 'a1', kind: 'image', filename: 'a.jpg' }],
      },
    ],
    price_entries: [
      {
        id: 'e1',
        catalog_item_id: 'svc_1',
        amount: 100,
        currency: 'USD',
        duration_minutes: 60,
        notes: 'Standard session',
        dimensions: { machine: 'Trio' },
      },
      {
        id: 'e2',
        catalog_item_id: 'svc_1',
        amount: 200,
        currency: 'USD',
        notes: 'Quadro machine',
        dimensions: { machine: 'Quadro' },
      },
    ],
  });
  assert.equal(items.length, 1);
  assert.equal(items[0].name, 'Laser hair removal');
  assert.equal(items[0].note, 'Full treatment details and aftercare');
  assert.equal(items[0].prices.length, 2);
  assert.equal(items[0].prices[0].subtitle, '1 hour');
  assert.equal(formatPriceFooter(items[0].prices), '2 price options · From $100');
  assert.equal(matchesServiceQuery(items[0], 'laser'), true);
  assert.equal(matchesServiceQuery(items[0], 'quadro'), true);
  assert.equal(matchesServiceQuery(items[0], 'tattoo'), false);
});

test('format helpers match screenshot copy', () => {
  assert.equal(formatMoney(100), '$100');
  assert.equal(formatMoney(0), 'Free');
  assert.equal(formatDuration(60), '1 hour');
  assert.equal(parseDurationMinutes('1 hour'), 60);
  assert.equal(parseAmount('$ 200'), 200);
  assert.equal(slugDimension('Body part'), 'body_part');
});

test('buildPriceEntry stores title in notes and details as dimensions', () => {
  const draft = {
    ...emptyPriceDraft(),
    title: 'Quadro · Full body',
    amountText: '200',
    details: [
      { key: 'Machine', value: 'Quadro' },
      { key: 'Body part', value: 'Full body' },
    ],
  };
  const row = buildPriceEntry('e9', 'svc_1', draft, 200);
  assert.equal(row.notes, 'Quadro · Full body');
  assert.equal(row.amount, 200);
  assert.deepEqual(row.dimensions, { machine: 'Quadro', body_part: 'Full body' });
});

test('patchCatalogItem writes name and note onto CM catalog fields', () => {
  const created = createCatalogItem('svc_new');
  const patched = patchCatalogItem(created, { name: 'HydraFacial', note: 'Glow treatment' });
  assert.equal(patched.item_type, 'service');
  assert.equal(patched.labels.en, 'HydraFacial');
  assert.equal(patched.description, 'Glow treatment');
});

test('parseServices keeps trailing spaces so Note and Name stay typeable', () => {
  const patched = patchCatalogItem(createCatalogItem('svc_space'), {
    name: 'HydraFacial ',
    note: 'Glow treatment ',
  });
  const items = parseServices({ catalog: [patched], price_entries: [] });
  assert.equal(items[0].name, 'HydraFacial ');
  assert.equal(items[0].note, 'Glow treatment ');
  const bookOnly = parseServices({
    catalog: [{ id: 'svc_book', labels: { en: 'X' }, notes: 'book_legacy' }],
    price_entries: [],
  });
  assert.equal(bookOnly[0].note, '');
});
