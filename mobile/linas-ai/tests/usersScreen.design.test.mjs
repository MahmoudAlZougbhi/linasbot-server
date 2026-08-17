/**
 * Users list / add / action-sheet design (no device required).
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);
const read = (...p) => readFileSync(src(...p), 'utf8');

test('list chrome matches Users handoff', () => {
  const screen = read('features/users/UsersScreen.tsx');
  const search = read('features/users/UsersSearchBar.tsx');
  const row = read('features/users/UserListRow.tsx');
  const ui = read('i18n/locales/usersUiEn.ts');
  assert.match(screen, /tr\('usersTitle'\)/);
  assert.match(screen, /tr\('usersSub'\)/);
  assert.match(screen, /UsersSearchBar/);
  assert.match(search, /tr\('usersAdd'\)/);
  assert.match(search, /feather\('plus'\)/);
  assert.match(search, /styles\.addSq/);
  assert.match(search, /styles\.row/);
  assert.doesNotMatch(screen, /headerRight/);
  assert.match(ui, /Manage team access/);
  assert.match(ui, /'\+ Add user'/);
  assert.match(ui, /Search members/);
  assert.match(row, /more-horizontal/);
  assert.match(row, /usersBlocked/);
  assert.match(row, /#22C55E/);
  assert.match(row, /#FEE2E2/);
  assert.match(row, /UserAvatar/);
});

test('listUsers keeps valid members when one row is legacy-shaped', () => {
  const api = read('features/users/usersApi.ts');
  assert.match(api, /parseTeamUser/);
  assert.match(api, /coercePermissions/);
  assert.match(api, /z\.array\(z\.unknown\(\)\)/);
  assert.match(api, /for \(const row of data\.users/);
});

test('Users load does not blank list when roles fail', () => {
  const screen = read('features/users/UsersScreen.tsx');
  assert.match(screen, /const list = await listUsers\(\)/);
  assert.match(screen, /setRoles\(await listRoles\(\)\)/);
  assert.doesNotMatch(screen, /Promise\.all\(\[listUsers\(\), listRoles\(\)\]\)/);
});

test('add user screen has login card, access grid, generate password', () => {
  const form = read('features/users/UserFormScreen.tsx');
  const login = read('features/users/UserLoginCard.tsx');
  const grid = read('features/users/UserAccessGrid.tsx');
  const password = read('features/users/UserPasswordField.tsx');
  const header = read('features/users/UserFormHeader.tsx');
  const ui = read('i18n/locales/usersUiEn.ts');
  assert.match(header, /chevron-left/);
  assert.match(form, /usersAddTitle/);
  assert.match(form, /usersAddSub/);
  assert.match(form, /UserLoginCard/);
  assert.match(form, /UserAccessGrid/);
  assert.match(login, /usersLoginDetails/);
  assert.match(login, /UserPasswordField/);
  assert.match(login, /UserRolePicker/);
  assert.match(password, /usersGenerate/);
  assert.match(password, /eye-off/);
  assert.match(grid, /usersView/);
  assert.match(grid, /usersManage/);
  assert.match(grid, /colors\.accent/);
  assert.match(ui, /Create login and choose access/);
  assert.match(ui, /They can change it after login/);
  assert.match(ui, /Choose what this user can view or manage/);
  assert.match(ui, /Subscription & Credits/);
  assert.match(ui, /Smart Follow-Up/);
});

test('action sheet has edit reset block delete and outlined cancel', () => {
  const sheet = read('features/users/UserActionSheet.tsx');
  const ui = read('i18n/locales/usersUiEn.ts');
  assert.match(sheet, /styles\.handle/);
  assert.match(sheet, /feather\('x'\)/);
  assert.match(sheet, /account-edit-outline/);
  assert.match(sheet, /key-outline/);
  assert.match(sheet, /account-cancel-outline/);
  assert.match(sheet, /trash-2/);
  assert.match(sheet, /usersDelete/);
  assert.match(sheet, /colors\.danger/);
  assert.match(sheet, /styles\.cancel/);
  assert.match(sheet, /borderColor:\s*colors\.accent/);
  assert.match(ui, /Profile, role, and app access/);
  assert.match(ui, /Set a new temporary password/);
  assert.match(ui, /Disable login without deleting data/);
  assert.match(ui, /Permanently remove this account/);
});

test('custom roles can be created and re-selected to fill permissions', () => {
  const picker = read('features/users/UserRolePicker.tsx');
  const form = read('features/users/UserFormScreen.tsx');
  const api = read('features/users/usersRolesApi.ts');
  assert.match(picker, /usersCreateRole/);
  assert.match(picker, /usersRoleName/);
  assert.match(form, /createRole/);
  assert.match(form, /permissionsFromRecord\(catalog\.permissions\)/);
  assert.match(form, /applyRole/);
  assert.match(api, /\/api\/auth\/users\/roles/);
});
