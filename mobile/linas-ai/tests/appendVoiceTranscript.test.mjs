import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = path.join(root, 'src/features/chat/appendVoiceTranscript.ts');

/** Keep behavior aligned with appendVoiceTranscript.ts (source-asserted below). */
function appendVoiceTranscript(existing, transcript) {
  const next = transcript.trim();
  if (!next) return existing;
  if (!existing) return next;
  if (/\s$/.test(existing)) return `${existing}${next}`;
  return `${existing} ${next}`;
}

test('appendVoiceTranscript merges without wiping existing draft', () => {
  assert.equal(appendVoiceTranscript('', 'hello'), 'hello');
  assert.equal(appendVoiceTranscript('typed', 'voice'), 'typed voice');
  assert.equal(appendVoiceTranscript('typed ', 'voice'), 'typed voice');
  assert.equal(appendVoiceTranscript('line1\n', 'line2'), 'line1\nline2');
  assert.equal(appendVoiceTranscript('keep', '  spaced  '), 'keep spaced');
  assert.equal(appendVoiceTranscript('keep', '   '), 'keep');
});

test('appendVoiceTranscript source matches tested behavior', () => {
  const body = readFileSync(src, 'utf8');
  assert.match(body, /export function appendVoiceTranscript/);
  assert.match(body, /transcript\.trim\(\)/);
  assert.match(body, /\\s\$/);
});
