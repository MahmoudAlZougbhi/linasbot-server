import { CM_HUB_PROGRESS_EXCLUDED, type CmSectionId } from './cmSections';

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

/** Owner-facing AI Setup progress — excludes hub-hidden sections. */
export function summarizeHubProgress(rows: HubProgressRow[]): HubProgressSummary {
  const hubRows = rows.filter(
    (r) => !CM_HUB_PROGRESS_EXCLUDED.includes(r.section as CmSectionId),
  );
  const complete = hubRows.filter((r) => r.status === 'complete').length;
  const total = hubRows.length;
  const incomplete = total - complete;
  return {
    complete,
    incomplete,
    total,
    percent: total ? Math.round((complete / total) * 100) : 0,
    missing_sections: hubRows.filter((r) => r.status !== 'complete').map((r) => r.section),
  };
}
