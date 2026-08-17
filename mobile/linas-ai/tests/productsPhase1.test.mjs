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
  it('exposes products hub entry in AI Setup mosaic layout', () => {
    const cm = read('features/cm/CmScreen.tsx');
    const hub = read('features/cm/AiSetupHubSections.tsx');
    const tile = read('features/cm/AiSetupSectionTile.tsx');
    assert.match(cm, /onOpenProducts/);
    assert.match(cm, /AiSetupHubSections/);
    assert.match(hub, /onOpenProducts/);
    assert.match(tile, /kind: 'products'/);
    assert.match(tile, /productsTitle/);
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
    assert.match(api, /MAX_PRODUCT_IMAGES = 5/);
    assert.match(api, /\/api\/mobile\/products\/media/);
  });

  it('Products list matches design: full-width Add, search, stock switch', () => {
    const screen = read('features/products/ProductsScreen.tsx');
    const list = read('features/products/ProductListView.tsx');
    assert.match(screen, /ProductListView/);
    assert.match(screen, /LinasSparkleIcon/);
    assert.match(list, /productsSearch/);
    assert.match(list, /Switch/);
    assert.match(list, /productsStockFooter/);
    assert.doesNotMatch(list, /AiSetupListHeader/);
  });

  it('registers products details navigation', () => {
    const nav = read('app/navigation.ts');
    assert.match(nav, /name: 'products_details'/);
    const tree = read('app/AppScreenTree.tsx');
    assert.match(tree, /ProductDetailsScreen/);
  });

  it('has products i18n keys in en/ar/fr', () => {
    for (const loc of ['productsSetupEn.ts', 'productsSetupAr.ts', 'productsSetupFr.ts']) {
      const src = read(`i18n/locales/${loc}`);
      assert.match(src, /productsTitle/);
      assert.match(src, /productsAddImage/);
      assert.match(src, /productsMaxImages/);
      assert.match(src, /productsImport/);
    }
  });
});
