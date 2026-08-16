import type { CmSectionId } from './cmSections';
import { isCmSectionId } from './cmSections';

/** Pending CM proposal overlay for Review-in-CM (local only — not saved). */
export type CmProposalReview = {
  section: string;
  proposalId?: string;
  /** Patch from propose_cm_patch preview.patch */
  patch?: Record<string, unknown>;
  /** Single article/FAQ row for item upserts */
  proposedItem?: Record<string, unknown>;
  articleId?: string;
  qaGroupId?: string;
};

export function isCmProposalSection(section: string): section is CmSectionId {
  return isCmSectionId(section);
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === 'object' && !Array.isArray(v);
}

/** Deep-merge like server `_merge_dict` for local proposal preview. */
export function mergeProposalPatch(
  base: Record<string, unknown>,
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    const current = out[key];
    if (isPlainObject(value) && isPlainObject(current)) {
      out[key] = mergeProposalPatch(current, value);
    } else {
      out[key] = value;
    }
  }
  return out;
}

/** Apply a focused article/FAQ item into section `items` without saving. */
export function applyProposedItem(
  base: Record<string, unknown>,
  item: Record<string, unknown>,
  idKey: 'id' | 'qa_group_id',
  listKey: 'items' | 'catalog' = 'items',
): Record<string, unknown> {
  const raw = base[listKey];
  const items = Array.isArray(raw)
    ? raw.filter((row): row is Record<string, unknown> => isPlainObject(row))
    : [];
  const id = String(item[idKey] || '');
  if (!id) {
    return { ...base, [listKey]: [...items, item] };
  }
  const idx = items.findIndex((row) => String(row[idKey] || '') === id);
  const next = [...items];
  if (idx >= 0) next[idx] = item;
  else next.push(item);
  return { ...base, [listKey]: next };
}
