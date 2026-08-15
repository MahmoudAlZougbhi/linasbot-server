import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

import { resolve as hookResolve } from './resolveTsSiblingHook.mjs';

const hookDir = dirname(fileURLToPath(import.meta.url));
const mobileSrcRoot = join(hookDir, '..', 'src');

async function runHook(specifier, parentPath) {
  const parentURL = pathToFileURL(parentPath).href;
  const calls = [];
  const nextResolve = async (nextSpecifier, context) => {
    calls.push({ nextSpecifier, parentURL: context.parentURL });
    return { url: pathToFileURL(join(dirname(parentPath), nextSpecifier)).href, format: 'module' };
  };
  const result = await hookResolve(specifier, { parentURL }, nextResolve);
  return { result, calls };
}

test('resolves a known extensionless sibling under mobile src', async () => {
  const parentPath = join(mobileSrcRoot, 'features', 'livechat', 'liveChatTypes.ts');
  const { calls } = await runHook('./liveChatHelpers', parentPath);
  assert.equal(calls.length, 1);
  assert.match(calls[0].nextSpecifier, /liveChatHelpers\.ts$/);
});

test('falls through when parent is outside mobile src', async () => {
  const outside = join(hookDir, 'outsideParent.mjs');
  const { calls } = await runHook('./Sibling', outside);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].nextSpecifier, './Sibling');
});

test('falls through for traversal that escapes src root', async () => {
  const parentPath = join(mobileSrcRoot, 'features', 'livechat', 'liveChatTypes.ts');
  const { calls } = await runHook('../../../package.json', parentPath);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].nextSpecifier, '../../../package.json');
});

test('falls through for explicit extension imports', async () => {
  const parentPath = join(mobileSrcRoot, 'features', 'livechat', 'liveChatTypes.ts');
  const { calls } = await runHook('./liveChatHelpers.ts', parentPath);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].nextSpecifier, './liveChatHelpers.ts');
});

test('resolves .tsx siblings when present', async () => {
  const parentPath = join(mobileSrcRoot, 'features', 'livechat', 'LiveChatInbox.tsx');
  const { calls } = await runHook('./ConversationRow', parentPath);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].nextSpecifier, './ConversationRow.tsx');
});
