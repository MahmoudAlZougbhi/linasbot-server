import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');

function read(rel) {
  return readFileSync(join(root, rel), 'utf8');
}

test('cm media upload prepares picker URIs before multipart append', () => {
  const api = read('features/cm/cmMediaApi.ts');
  const formData = read('api/formDataFile.ts');
  const attach = read('features/cm/cmMediaAttach.ts');

  assert.match(api, /prepareUploadUri/);
  assert.match(api, /kind: z\.enum\(\['image', 'video', 'file'\]\)/);
  assert.match(formData, /export async function prepareUploadUri/);
  assert.match(formData, /copyAsync/);
  assert.match(attach, /finally\s*\{\s*setUploading\(false\)/);
});

test('knowledge media hook clears spinner via shared upload runner', () => {
  const hook = read('features/cm/knowledge/useKnowledgeMedia.ts');
  assert.match(hook, /runCmMediaUpload/);
  assert.doesNotMatch(hook, /uploadCmArticleMedia/);
});
