import type { CmSectionCard } from './cmSections';

/** Full-width hub rows appear in this order at the top of AI Setup. */
export const AI_SETUP_FULL_WIDTH_IDS = ['knowledge', 'dynamic_messages', 'services'] as const;

export type HubItem =
  | { kind: 'section'; tile: CmSectionCard }
  | { kind: 'products' };

export type HubFullRow = { type: 'full'; item: HubItem };
export type HubMosaicRow = { type: 'mosaic'; big: HubItem; smalls: HubItem[] };
export type HubRow = HubFullRow | HubMosaicRow;

const FULL_WIDTH_SET = new Set<string>(AI_SETUP_FULL_WIDTH_IDS);

/** Partition hub tiles into full-width rows then alternating big + two-small mosaic rows. */
export function buildAiSetupHubRows(
  tiles: CmSectionCard[],
  includeProducts: boolean,
): HubRow[] {
  const byId = new Map(tiles.map((tile) => [tile.id, tile]));
  const rows: HubRow[] = [];

  for (const id of AI_SETUP_FULL_WIDTH_IDS) {
    const tile = byId.get(id);
    if (tile) rows.push({ type: 'full', item: { kind: 'section', tile } });
  }

  const mosaicItems: HubItem[] = [];
  let productsPlaced = false;

  for (const tile of tiles) {
    if (FULL_WIDTH_SET.has(tile.id)) continue;
    mosaicItems.push({ kind: 'section', tile });
    if (includeProducts && tile.id === 'prices') {
      mosaicItems.push({ kind: 'products' });
      productsPlaced = true;
    }
  }

  if (includeProducts && !productsPlaced) {
    mosaicItems.push({ kind: 'products' });
  }

  for (let i = 0; i < mosaicItems.length; i += 3) {
    const chunk = mosaicItems.slice(i, i + 3);
    if (!chunk.length) continue;
    rows.push({ type: 'mosaic', big: chunk[0], smalls: chunk.slice(1) });
  }

  return rows;
}
