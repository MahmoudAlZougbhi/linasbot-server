/**
 * View/Manage grid maps onto existing permission keys.
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const access = readFileSync(
  join(root, 'src/features/users/usersAccess.ts'),
  'utf8',
);
const perms = readFileSync(
  join(root, 'src/features/users/usersPermissions.ts'),
  'utf8',
);

test('access screens map onto existing RBAC keys', () => {
  assert.match(access, /id: 'dashboard'[\s\S]*view: \['dashboard'\][\s\S]*manage: \['analytics'\]/);
  assert.match(access, /id: 'liveChat'[\s\S]*view: \['liveChat'\][\s\S]*manage: \['liveChat'\]/);
  assert.match(access, /id: 'requests'[\s\S]*view: \['requests'\]/);
  assert.match(access, /manage: \['requestsManage', 'requestsNotify', 'requestsManualChat'\]/);
  assert.match(access, /id: 'aiSetup'[\s\S]*view: \['contentManagers'\][\s\S]*manage: \['contentPublish'\]/);
  assert.match(access, /id: 'smartAnswers'[\s\S]*view: \['contentManagers'\]/);
  assert.match(access, /id: 'smartFollowUp'[\s\S]*view: \['contentManagers'\]/);
  assert.match(access, /id: 'integrations'[\s\S]*view: \['settings'\]/);
  assert.match(access, /id: 'users'[\s\S]*view: \['userManagement'\]/);
  assert.match(access, /id: 'subscription'[\s\S]*view: \['settings'\]/);
  assert.match(access, /id: 'settings'[\s\S]*view: \['settings'\]/);
  assert.match(access, /if \(column === 'manage' && value\)/);
  assert.match(access, /if \(column === 'view' && !value\)/);
});

test('role templates still match backend system roles', () => {
  assert.match(perms, /ASSIGNABLE_ROLES = \['admin', 'operator', 'viewer'\]/);
  assert.match(perms, /userManagement: true/);
  assert.match(perms, /operator: \{/);
  assert.match(perms, /viewer: \{/);
  assert.match(perms, /isAssignableRole/);
  assert.match(perms, /permissionsFromRecord/);
});
