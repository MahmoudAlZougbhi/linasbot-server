import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('nav drawer Smart Follow-Up + AI Setup featured tile', () => {
  it('drawer module order matches product grid (cm featured separately)', () => {
    const modules = read('features/nav/drawerModules.ts');
    assert.match(modules, /export const FEATURED_AI_SETUP/);
    assert.match(modules, /FEATURED_AI_SETUP: DrawerModule = \{[\s\S]*?id:\s*'cm'/);

    const gridBlock = modules.match(
      /export const DRAWER_MODULES: DrawerModule\[] = \[([\s\S]*?)\];/,
    );
    assert.ok(gridBlock, 'DRAWER_MODULES array missing');
    assert.doesNotMatch(gridBlock[1], /id:\s*'cm'/);

    const gridIds = [...gridBlock[1].matchAll(/id:\s*'([^']+)'/g)].map((m) => m[1]);
    assert.deepEqual(gridIds, [
      'dashboard',
      'smartFollowUp',
      'faq',
      'livechat',
      'requests',
      'integrations',
      'users',
      'subscription',
    ]);
  });

  it('drawerGridModules puts AI Setup first in the 3×3 grid', () => {
    const modules = read('features/nav/drawerModules.ts');
    assert.match(modules, /drawerGridModules/);
    assert.match(modules, /\[FEATURED_AI_SETUP, \.\.\.visibleDrawerModules/);
  });

  it('NavDrawer renders 3×3 grid via DrawerNavGrid', () => {
    const drawer = read('features/nav/NavDrawer.tsx');
    assert.match(drawer, /DrawerNavGrid/);
    assert.match(drawer, /DrawerHeader/);
    assert.match(drawer, /DrawerRecents/);
    assert.match(drawer, /DrawerFooter/);
    assert.doesNotMatch(drawer, /NavDrawerAiSetupTile/);
  });

  it('AI Setup tile status helper covers continue / complete / needs attention', () => {
    const status = read('features/nav/aiSetupTileStatus.ts');
    assert.match(status, /resolveAiSetupTileStatus/);
    assert.match(status, /needs_attention/);
    assert.match(status, /fetchFailed/);
    assert.match(status, /incomplete\s*>\s*0\s*&&\s*opts\.published/);
  });

  it('wires smartFollowUp through control area, icons, navigation, and screen tree', () => {
    assert.match(read('features/control/controlAreas.ts'), /smartFollowUp/);
    assert.match(read('features/nav/moduleIcons.ts'), /smartFollowUp:\s*ion\('timer-outline'\)/);
    assert.match(read('app/navigation.ts'), /name:\s*'smartFollowUp'/);
    assert.match(read('app/AppShell.tsx'), /area === 'smartFollowUp'/);
    assert.match(read('app/moduleNav.ts'), /case 'smartFollowUp'/);
    const tree = read('app/AppScreenTree.tsx');
    assert.match(tree, /SmartFollowUpScreen/);
    assert.ok(
      tree.includes("KeepMountedPane key={`smartFollowUp-${authEpoch}`}"),
      'missing keep-mounted pane for smartFollowUp',
    );
  });

  it('Smart Follow-Up screen uses channels grid and save changes', () => {
    const screen = read('features/smartFollowUp/SmartFollowUpScreen.tsx');
    assert.match(screen, /SmartFollowUpChannelsCard/);
    assert.match(screen, /channels_enabled/);
    assert.match(screen, /sfuSaveChanges/);
    const api = read('features/smartFollowUp/smartFollowUpApi.ts');
    assert.match(api, /\/api\/whatsapp\/smart-followup\/settings/);
  });

  it('i18n exposes Smart Follow-Up title keys in en/ar/fr', () => {
    for (const lang of ['En', 'Ar', 'Fr']) {
      const src = readFileSync(join(root, `src/i18n/locales/smartFollowUp${lang}.ts`), 'utf8');
      assert.match(src, /navSmartFollowUp:/);
      assert.match(src, /sfuTitle:/);
      assert.match(src, /sfuSubtitle:/);
      assert.match(src, /aiSetupStatusContinue:/);
    }
    assert.match(
      readFileSync(join(root, 'src/i18n/locales/smartFollowUpAr.ts'), 'utf8'),
      /المتابعة الذكية/,
    );
    assert.match(read('i18n/locales/en.ts'), /smartFollowUpEn/);
    assert.match(read('i18n/locales/ar.ts'), /smartFollowUpAr/);
    assert.match(read('i18n/locales/fr.ts'), /smartFollowUpFr/);
  });
});
