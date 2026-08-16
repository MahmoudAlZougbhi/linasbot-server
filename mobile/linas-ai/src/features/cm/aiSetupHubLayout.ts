import type { CmSectionCard } from './cmSections';

/** Full-width hub rows appear in this order at the top of AI Setup. */
export const AI_SETUP_FULL_WIDTH_IDS = ['ai_basics', 'knowledge'] as const;

/** Side-by-side pair rows (left → right). Use `products` for the Products tile. */
export const AI_SETUP_PAIR_ROWS: readonly (readonly (CmSectionCard['id'] | 'products')[])[] = [
  ['opening_hours', 'branches'],
  ['prices', 'products'],
  ['comments', 'requests_appointments'],
];

export type HubItem =
  | { kind: 'section'; tile: CmSectionCard }
  | { kind: 'products' };

export type HubFullRow = { type: 'full'; item: HubItem };
export type HubPairRow = { type: 'pair'; left: HubItem; right: HubItem };
export type HubRow = HubFullRow | HubPairRow;

function resolveHubItem(
  id: CmSectionCard['id'] | 'products',
  byId: Map<string, CmSectionCard>,
  includeProducts: boolean,
): HubItem | null {
  if (id === 'products') {
    return includeProducts ? { kind: 'products' } : null;
  }
  const tile = byId.get(id);
  return tile ? { kind: 'section', tile } : null;
}

/** Build hub rows: full-width AI Basics + Knowledge, then three pair mosaic rows. */
export function buildAiSetupHubRows(
  tiles: CmSectionCard[],
  includeProducts: boolean,
): HubRow[] {
  const byId = new Map(tiles.map((tile) => [tile.id, tile]));
  const rows: HubRow[] = [];

  for (const id of AI_SETUP_FULL_WIDTH_IDS) {
    const item = resolveHubItem(id, byId, includeProducts);
    if (item) rows.push({ type: 'full', item });
  }

  for (const [leftId, rightId] of AI_SETUP_PAIR_ROWS) {
    const left = resolveHubItem(leftId, byId, includeProducts);
    const right = resolveHubItem(rightId, byId, includeProducts);
    if (left && right) {
      rows.push({ type: 'pair', left, right });
    } else if (left) {
      rows.push({ type: 'full', item: left });
    } else if (right) {
      rows.push({ type: 'full', item: right });
    }
  }

  return rows;
}
