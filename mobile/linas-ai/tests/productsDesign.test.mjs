/**
 * AI Products design handoff — list / wizard / details match screenshots.
 * Run: node --test mobile/linas-ai/tests/productsDesign.test.mjs
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

describe('AI Products design screens', () => {
  it('list uses full-width Add, search, stock Switch, and footer tip', () => {
    const list = read('features/products/ProductListView.tsx');
    const screen = read('features/products/ProductsScreen.tsx');
    assert.match(list, /productsAdd/);
    assert.match(list, /productsSearch/);
    assert.match(list, /Switch/);
    assert.match(list, /productsStockFooter/);
    assert.match(list, /onToggleStock/);
    assert.match(screen, /LinasSparkleIcon/);
    assert.match(screen, /updateProductAvailability/);
    assert.match(screen, /onOpenDetails/);
    assert.doesNotMatch(list, /AiSetupListHeader/);
  });

  it('add/edit is a two-step Details → Media & links wizard', () => {
    const add = read('features/products/AddProductScreen.tsx');
    const details = read('features/products/ProductDetailsStep.tsx');
    const media = read('features/products/ProductMediaLinksStep.tsx');
    const channel = read('features/products/ProductChannelLinksCard.tsx');
    assert.match(add, /ProductStepper/);
    assert.match(add, /ProductDetailsStep/);
    assert.match(add, /ProductMediaLinksStep/);
    assert.match(details, /productsContinue/);
    assert.match(media, /productsSave/);
    assert.match(media, /productsAddVideo/);
    assert.match(media, /productsAddFile/);
    assert.match(media, /productsAddShareLink/);
    assert.match(media, /ProductChannelLinksCard/);
    assert.match(channel, /productsAddChannelLink/);
    assert.match(media, /MAX_PRODUCT_IMAGES/);
  });

  it('product details screen supports Edit and Delete', () => {
    const details = read('features/products/ProductDetailsScreen.tsx');
    const tree = read('app/AppScreenTree.tsx');
    const nav = read('app/navigation.ts');
    assert.match(details, /productsDetailsTitle/);
    assert.match(details, /productsEdit/);
    assert.match(details, /productsDeleteProduct/);
    assert.match(nav, /products_details/);
    assert.match(tree, /ProductDetailsScreen/);
  });

  it('API allows 5 images and shareable/channel asset link helpers', () => {
    const api = read('features/products/productsApi.ts');
    const model = read('features/products/productModel.ts');
    assert.match(api, /MAX_PRODUCT_IMAGES = 5/);
    assert.match(api, /updateProductAvailability/);
    assert.match(api, /uploadProductMedia/);
    assert.match(model, /CHANNEL_PREFIX/);
    assert.match(model, /ASSET_VIDEO/);
    assert.match(model, /mergeProductLinks/);
  });

  it('i18n keys exist in en/ar/fr', () => {
    for (const loc of ['productsSetupEn.ts', 'productsSetupAr.ts', 'productsSetupFr.ts']) {
      const src = read(`i18n/locales/${loc}`);
      assert.match(src, /productsStockFooter/);
      assert.match(src, /productsStepMedia/);
      assert.match(src, /productsDetailsTitle/);
      assert.match(src, /productsChannelInfo/);
      assert.match(src, /Maximum 5|حد أقصى 5|max\. 5|حتى 5/);
    }
  });
});
