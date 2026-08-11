import { z } from 'zod';

import { apiFetch } from '../../api/client';

const ProgressRowSchema = z.object({
  section: z.string(),
  status: z.enum(['complete', 'incomplete']),
  revision: z.number().optional(),
});

export const CmSetupProgressSchema = z
  .object({
    success: z.literal(true),
    progress: z.array(ProgressRowSchema).optional(),
    summary: z
      .object({
        complete: z.number(),
        incomplete: z.number(),
        total: z.number(),
        percent: z.number(),
        published: z.boolean().optional(),
        missing_sections: z.array(z.string()).optional(),
      })
      .optional(),
  })
  .passthrough();

export type CmSetupProgress = z.infer<typeof CmSetupProgressSchema>;
export type CmProgressRow = z.infer<typeof ProgressRowSchema>;

/** Real CM fill progress (complete vs still-default / missing). */
export async function fetchCmSetupProgress(): Promise<CmSetupProgress> {
  return apiFetch('/api/cm/setup-chat/progress', { schema: CmSetupProgressSchema });
}

export function buildFillMissingPrompt(missing: string[], titles: Record<string, string>): string {
  const labels = missing.map((id) => titles[id] || id.replace(/_/g, ' '));
  if (!labels.length) {
    return (
      'Review my AI Setup. Confirm what is already filled, ' +
      'what still needs polish, and help me publish when ready. Use read_cm and setup_next_step.'
    );
  }
  const listed = labels.slice(0, 8).join(', ');
  const extra = labels.length > 8 ? ` (+${labels.length - 8} more)` : '';
  return (
    `Help me finish AI Setup. These sections are still incomplete: ${listed}${extra}. ` +
    'Use read_account_summary, read_cm, and setup_next_step. ' +
    'Fill the missing pieces with me one section at a time — start with the first incomplete section now.'
  );
}
