import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src');

function read(rel) {
  return readFileSync(join(root, rel), 'utf8');
}

describe('AppModal chrome', () => {
  it('uses overFullScreen transparent shell for iOS black-screen fix', () => {
    const src = read('components/AppModal.tsx');
    assert.match(src, /transparent/);
    assert.match(src, /statusBarTranslucent/);
    assert.match(src, /presentationStyle="overFullScreen"/);
    assert.match(src, /absoluteFillObject/);
  });

  it('remaps slide animation to fade to avoid black bar flash', () => {
    const src = read('components/AppModal.tsx');
    assert.match(src, /animationType === 'slide' \? 'fade'/);
  });

  it('ModalScrim uses theme overlay token and full-screen fill', () => {
    const src = read('components/ModalScrim.tsx');
    assert.match(src, /colors\.overlay/);
    assert.match(src, /absoluteFillObject/);
    assert.doesNotMatch(src, /backgroundColor:\s*['"]#000/);
  });

  it('feature modals use AppModal instead of raw Modal', () => {
    const offenders = [
      'features/auth/AuthGateModal.tsx',
      'features/billing/BuyCreditsSheet.tsx',
      'features/billing/DowngradeConfirmSheet.tsx',
      'features/settings/SettingsChrome.tsx',
      'features/requests/RequestFilterSheet.tsx',
      'features/dashboard/sections/DashboardDateRangeSheet.tsx',
      'features/users/UsersScreen.tsx',
      'features/chat/ComposerPlusMenu.tsx',
    ];
    for (const file of offenders) {
      const src = read(file);
      assert.match(src, /AppModal/, `${file} should use AppModal`);
      assert.doesNotMatch(src, /<Modal[\s>]/, `${file} should not use raw Modal`);
    }
  });
});
