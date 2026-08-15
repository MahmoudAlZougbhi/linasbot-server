/**
 * Users permission gate for legacy owner role + tenant list access.
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const perms = readFileSync(join(root, 'src/features/users/usersPermissions.ts'), 'utf8');

test('owner and platform_owner can manage users', () => {
  assert.match(perms, /user\.role === 'platform_owner' \|\| user\.role === 'owner'/);
  assert.match(perms, /role === 'admin' \|\| role === 'owner' \|\| role === 'platform_owner'/);
  assert.doesNotMatch(perms, /if \(user\.role === 'admin'/);
});
