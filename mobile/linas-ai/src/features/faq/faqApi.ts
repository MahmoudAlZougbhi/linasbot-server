import { z } from 'zod';

import { apiFetch } from '../../api/client';

const FaqVariantSchema = z
  .object({
    language: z.string().optional(),
    question: z.string().optional(),
    answer: z.string().optional(),
  })
  .passthrough();

const FaqGroupSchema = z
  .object({
    qa_group_id: z.string(),
    variants: z.array(FaqVariantSchema).optional(),
    status: z.string().optional(),
    incomplete: z.boolean().optional(),
    reviewed: z.boolean().optional(),
    source_language: z.string().optional(),
  })
  .passthrough();

const EntitlementSchema = z
  .object({
    faq_enabled: z.boolean().optional(),
    faq_max_entries: z.number().optional(),
    faq_used_entries: z.number().optional(),
    faq_remaining_entries: z.number().optional(),
    quota_display: z.string().optional(),
    at_limit: z.boolean().optional(),
    upgrade_message: z.string().nullable().optional(),
    plan_id: z.string().optional(),
  })
  .passthrough();

const ListSchema = z
  .object({
    success: z.literal(true),
    data: z.array(FaqGroupSchema).optional(),
    entitlement: EntitlementSchema.optional(),
    quota_display: z.string().optional(),
    smart_answer_languages: z.array(z.string()).optional(),
    catalog: z
      .array(
        z
          .object({
            id: z.string(),
            label: z.string(),
            native: z.string().optional(),
          })
          .passthrough(),
      )
      .optional(),
  })
  .passthrough();

const CreateSchema = z
  .object({
    success: z.literal(true),
    entitlement: EntitlementSchema.optional(),
    qa_group_id: z.string().optional(),
  })
  .passthrough();

const OkSchema = z
  .object({
    success: z.literal(true),
  })
  .passthrough();

export type FaqGroup = z.infer<typeof FaqGroupSchema>;
export type FaqEntitlement = z.infer<typeof EntitlementSchema>;

export type FaqListResult = {
  items: FaqGroup[];
  entitlement: FaqEntitlement | null;
  quotaDisplay: string | null;
  smartAnswerLanguages: string[];
  catalog: Array<{ id: string; label: string; native?: string }>;
};

export async function listFaq(params?: {
  q?: string;
  status?: string;
  language?: string;
  include_archived?: boolean;
}): Promise<FaqListResult> {
  const qs = new URLSearchParams();
  if (params?.q) qs.set('q', params.q);
  if (params?.status) qs.set('status', params.status);
  if (params?.language) qs.set('language', params.language);
  if (params?.include_archived) qs.set('include_archived', 'true');
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  const res = await apiFetch(`/api/cm/faq${suffix}`, { schema: ListSchema });
  return {
    items: Array.isArray(res.data) ? res.data : [],
    entitlement: res.entitlement ?? null,
    quotaDisplay: typeof res.quota_display === 'string' ? res.quota_display : res.entitlement?.quota_display ?? null,
    smartAnswerLanguages: Array.isArray(res.smart_answer_languages) ? res.smart_answer_languages.map(String) : [],
    catalog: Array.isArray(res.catalog) ? res.catalog : [],
  };
}

export async function saveSmartAnswerLanguages(input: {
  languages: string[];
  translateExisting?: boolean;
}): Promise<void> {
  await apiFetch('/api/cm/faq/smart-answer-languages', {
    method: 'PUT',
    schema: OkSchema,
    body: JSON.stringify({
      smart_answer_languages: input.languages,
      translate_existing: Boolean(input.translateExisting),
    }),
  });
}

export async function translateExistingSmartAnswers(language: string): Promise<void> {
  await apiFetch('/api/cm/faq/smart-answer-languages/translate-existing', {
    method: 'POST',
    schema: OkSchema,
    body: JSON.stringify({ language }),
  });
}

export async function createFaq(input: {
  question: string;
  answer: string;
  language?: string;
}): Promise<void> {
  await apiFetch('/api/cm/faq', {
    method: 'POST',
    schema: CreateSchema,
    body: JSON.stringify({
      question: input.question,
      answer: input.answer,
      language: input.language || 'ar',
    }),
  });
}

export async function archiveFaq(qaGroupId: string): Promise<void> {
  await apiFetch(`/api/cm/faq/${encodeURIComponent(qaGroupId)}/archive`, {
    method: 'POST',
    schema: OkSchema,
  });
}

export async function patchFaqVariant(
  qaGroupId: string,
  language: string,
  input: { question: string; answer: string },
): Promise<void> {
  await apiFetch(`/api/cm/faq/${encodeURIComponent(qaGroupId)}/variants/${encodeURIComponent(language)}`, {
    method: 'PATCH',
    schema: OkSchema,
    body: JSON.stringify({
      question: input.question,
      answer: input.answer,
    }),
  });
}

export async function regenerateFaq(qaGroupId: string): Promise<void> {
  await apiFetch(`/api/cm/faq/${encodeURIComponent(qaGroupId)}/regenerate`, {
    method: 'POST',
    schema: OkSchema,
    body: JSON.stringify({}),
  });
}
