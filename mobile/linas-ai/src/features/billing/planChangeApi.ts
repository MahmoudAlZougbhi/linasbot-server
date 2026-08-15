import { z } from 'zod';

import { apiFetch } from '../../api/client';
import type { PlanId } from './planCatalog';

const ResponseSchema = z.object({ success: z.boolean() }).passthrough();

export type PendingDowngrade = {
  planId: PlanId;
  displayName: string;
  effectiveAt: number;
};

export function parsePendingDowngrade(raw: unknown): PendingDowngrade | null {
  if (!raw || typeof raw !== 'object') return null;
  const row = raw as Record<string, unknown>;
  const planId = typeof row.plan_id === 'string' ? row.plan_id : null;
  const effectiveAt = typeof row.effective_at === 'number' ? row.effective_at : null;
  if (!planId || effectiveAt == null) return null;
  return {
    planId: planId as PlanId,
    displayName: typeof row.display_name === 'string' ? row.display_name : planId,
    effectiveAt,
  };
}

export async function scheduleDowngrade(planId: PlanId): Promise<void> {
  await apiFetch('/api/entitlements/schedule-downgrade', {
    method: 'POST',
    body: JSON.stringify({ plan_id: planId }),
    schema: ResponseSchema,
  });
}

export async function cancelPendingDowngrade(): Promise<void> {
  await apiFetch('/api/entitlements/pending-plan-change', {
    method: 'DELETE',
    schema: ResponseSchema,
  });
}
