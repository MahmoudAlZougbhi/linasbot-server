import {
  CM_HUB_PRODUCTS_PROGRESS_ID,
  CM_HUB_PROGRESS_SECTION_IDS,
  CM_HUB_PROGRESS_TOTAL,
} from './cmSections';

export type HubProgressRow = {
  section: string;
  status: 'complete' | 'incomplete';
};

export type HubProgressSummary = {
  complete: number;
  incomplete: number;
  total: number;
  percent: number;
  missing_sections: string[];
};

export type SummarizeHubProgressOptions = {
  /** When true, Products hub tile counts as complete. */
  productsComplete?: boolean;
};

/** Owner-facing AI Setup progress — only the 7 hub tiles (6 CM + Products). */
export function summarizeHubProgress(
  rows: HubProgressRow[],
  opts?: SummarizeHubProgressOptions,
): HubProgressSummary {
  const byId = new Map(rows.map((r) => [r.section, r.status]));
  const missing: string[] = [];
  let complete = 0;

  for (const id of CM_HUB_PROGRESS_SECTION_IDS) {
    if (byId.get(id) === 'complete') {
      complete += 1;
    } else {
      missing.push(id);
    }
  }

  if (opts?.productsComplete) {
    complete += 1;
  } else {
    missing.push(CM_HUB_PRODUCTS_PROGRESS_ID);
  }

  const total = CM_HUB_PROGRESS_TOTAL;
  const incomplete = total - complete;
  return {
    complete,
    incomplete,
    total,
    percent: total ? Math.round((complete / total) * 100) : 0,
    missing_sections: missing,
  };
}
