/**
 * AI Products Phase 1 — hub entry, navigation, API client.
 * Run: node --test mobile/linas-ai/tests/productsPhase1.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('AI Products Phase 1 mobile', () => {
  it('exposes products hub card in AI Setup', () => {
    const cm = read('features/cm/CmScreen.tsx');
    assert.match(cm, /AiSetupProductsCard/);
    assert.match(cm, /onOpenProducts/);
  });

  it('registers products navigation screens', () => {
    const nav = read('app/navigation.ts');
    assert.match(nav, /name: 'products'/);
    assert.match(nav, /name: 'products_import'/);
    assert.match(nav, /name: 'products_add'/);
    assert.match(nav, /name: 'products_edit'/);
    const tree = read('app/AppScreenTree.tsx');
    assert.match(tree, /ProductsScreen/);
    assert.match(tree, /ProductsImportScreen/);
    assert.match(tree, /AddProductScreen/);
  });

  it('mobile API client targets import preview', () => {
    const api = read('features/products/productsApi.ts');
    assert.match(api, /\/api\/mobile\/products\/import\/preview/);
    assert.match(api, /previewProductsImport/);
    assert.match(api, /importProducts/);
  });

  it('mobile API client targets /api/mobile/products', () => {
    const api = read('features/products/productsApi.ts');
    assert.match(api, /\/api\/mobile\/products/);
    assert.match(api, /MAX_PRODUCT_IMAGES = 3/);
    assert.match(api, /\/api\/mobile\/products\/media/);
  });

  it('has products i18n keys in en/ar/fr', () => {
    for (const loc of ['aiSetupEn.ts', 'aiSetupAr.ts', 'aiSetupFr.ts']) {
      const src = read(`i18n/locales/${loc}`);
      assert.match(src, /productsTitle/);
      assert.match(src, /productsAddImage/);
      assert.match(src, /productsMaxImages/);
      assert.match(src, /productsImport/);
    }
  });
});
