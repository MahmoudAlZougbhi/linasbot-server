/**
 * Knowledge list helpers — word count, media summary, locations row.
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  buildKnowledgeList,
  countMedia,
  countWords,
  formatBytes,
  formatDuration,
  formatMediaSummary,
  formatUpdatedStamp,
  isLocationsKnowledgeTitle,
  isValidHttpUrl,
  itemToRecord,
  parseKnowledgeItem,
} from '../src/features/cm/knowledge/knowledgeModel.ts';

describe('knowledgeModel', () => {
  it('counts words live', () => {
    assert.equal(countWords(''), 0);
    assert.equal(countWords('  one two three  '), 3);
  });

  it('summarizes mixed resources like the screenshot', () => {
    const counts = countMedia([
      { id: '1', kind: 'image', title: '', description: '', caption: '', mime: 'image/jpeg', filename: 'a.jpg', size: 1, url: '', duration_seconds: null },
      { id: '2', kind: 'image', title: '', description: '', caption: '', mime: 'image/png', filename: 'b.png', size: 1, url: '', duration_seconds: null },
      { id: '3', kind: 'video', title: '', description: '', caption: '', mime: 'video/mp4', filename: 'c.mp4', size: 1, url: '', duration_seconds: 84 },
      { id: '4', kind: 'file', title: '', description: '', caption: '', mime: 'application/pdf', filename: 'd.pdf', size: 1, url: '', duration_seconds: null },
    ]);
    assert.equal(formatMediaSummary(counts), '2 images • 1 video • 1 PDF');
    assert.equal(formatMediaSummary(countMedia([])), 'Text only');
    assert.equal(formatDuration(84), '01:24');
    assert.equal(formatBytes(1.8 * 1024 * 1024), '1.8 MB');
  });

  it('builds a locations shortcut row and hides duplicate articles', () => {
    const items = [
      parseKnowledgeItem({ id: 'k1', title: 'Laser hair removal guide', body: 'x', status: 'active' }),
      parseKnowledgeItem({ id: 'k2', title: 'Opening hours & locations', body: 'old', status: 'active' }),
    ];
    const rows = buildKnowledgeList(items, '');
    assert.equal(rows.filter((row) => row.type === 'locations').length, 1);
    assert.equal(rows.filter((row) => row.type === 'article').length, 1);
    assert.equal(isLocationsKnowledgeTitle('Opening hours & locations'), true);
  });

  it('formats updated stamps and validates links', () => {
    const now = new Date('2026-08-16T12:00:00');
    assert.equal(formatUpdatedStamp(now.toISOString(), now), 'today');
    assert.equal(formatUpdatedStamp('2026-08-14T12:00:00', now), 'Aug 14');
    assert.equal(isValidHttpUrl('https://example.com/a'), true);
    assert.equal(isValidHttpUrl('ftp://example.com'), false);
  });

  it('persists resource title and description', () => {
    const item = parseKnowledgeItem({
      id: 'k1',
      title: 'Laser Hair Removal Women',
      body: 'Women file',
      attachments: [
        {
          id: 'res_women_before',
          kind: 'image',
          title: 'Women Before',
          description: 'Send for women before photos.',
          filename: 'women-before.png',
        },
      ],
    });
    assert.equal(item.attachments[0].title, 'Women Before');
    assert.equal(item.attachments[0].description, 'Send for women before photos.');
    const dumped = itemToRecord(item);
    const atts = dumped.attachments;
    assert.ok(Array.isArray(atts));
    assert.equal(atts[0].title, 'Women Before');
    assert.equal(atts[0].caption, 'Send for women before photos.');
  });
});
