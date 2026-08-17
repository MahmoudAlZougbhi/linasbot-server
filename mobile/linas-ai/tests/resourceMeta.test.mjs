import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  moveById,
  parseResourceFields,
  resourceMetaError,
  serializeResourceFields,
  suggestedTitleFromFilename,
} from '../src/features/cm/resources/resourceMeta.ts';

describe('resourceMeta', () => {
  it('requires title and short description', () => {
    assert.equal(resourceMetaError('image', { title: '', description: 'x' }), 'title');
    assert.equal(resourceMetaError('image', { title: 'Before', description: '' }), 'description');
    assert.equal(resourceMetaError('link', { title: 'Book', description: 'Send when booking' }), 'url');
    assert.equal(
      resourceMetaError('link', { title: 'Book', description: 'Send when booking' }, 'https://example.test'),
      null,
    );
  });

  it('reads description from caption for legacy rows', () => {
    assert.deepEqual(parseResourceFields({ caption: 'Use when asked', filename: 'a.png' }), {
      title: '',
      description: 'Use when asked',
    });
    assert.equal(serializeResourceFields({ title: 'Women Before', description: 'Send for women' }).caption, 'Send for women');
  });

  it('reorders without mixing ids', () => {
    const moved = moveById(
      [
        { id: 'a', sort_order: 0 },
        { id: 'b', sort_order: 1 },
        { id: 'c', sort_order: 2 },
      ],
      'c',
      -1,
    );
    assert.deepEqual(
      moved.map((row) => row.id),
      ['a', 'c', 'b'],
    );
  });

  it('suggests a title from filename without publishing', () => {
    assert.equal(suggestedTitleFromFilename('women-before.png'), 'women before');
    assert.equal(suggestedTitleFromFilename('7C7332B2-E048-4A1B-9C3D-1234567890AB.mp4'), '');
    assert.equal(suggestedTitleFromFilename('7c7332b2_e048_4a1b_9c3d_1234567890ab.jpg'), '');
  });
});
