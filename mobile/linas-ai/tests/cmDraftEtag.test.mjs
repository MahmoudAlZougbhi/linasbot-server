/**
 * CM draft ETag / If-Match — quoted server tags must be sent unchanged.
 * Run: node --test mobile/linas-ai/tests/cmDraftEtag.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { resolveCmEtag } from '../src/features/cm/cmEtag.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

const QUOTED = '"3-ab12cd34ef56ab78"';

describe('CM draft ETag', () => {
  it('prefers the JSON body etag and never strips quotes', () => {
    assert.equal(resolveCmEtag(QUOTED, QUOTED), QUOTED);
    assert.equal(resolveCmEtag(QUOTED, '3-ab12cd34ef56ab78'), QUOTED);
    assert.equal(resolveCmEtag(undefined, QUOTED), QUOTED);
    assert.equal(resolveCmEtag('', QUOTED, 'fallback'), QUOTED);
    assert.equal(resolveCmEtag(null, null, QUOTED), QUOTED);
    assert.notEqual(resolveCmEtag(QUOTED, QUOTED), QUOTED.replace(/^"|"$/g, ''));
  });

  it('get/put draft use resolveCmEtag and do not strip header quotes', () => {
    const api = read('features/cm/cmApi.ts');
    const draft = read('features/cm/useCmDraft.ts');
    const multi = read('features/cm/useCmMultiDraft.ts');
    assert.match(api, /resolveCmEtag/);
    assert.doesNotMatch(api, /replace\(\/\^\\\|"\\\|\/\$\/g/);
    assert.match(draft, /saveLock/);
    assert.match(multi, /saveLock/);
    assert.match(draft, /Someone else saved this section/);
    assert.match(multi, /Someone else saved this section/);
  });
});
