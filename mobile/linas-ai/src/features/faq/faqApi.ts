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
  })
  .passthrough();

const ListSchema = z
  .object({
    success: z.literal(true),
    data: z.array(FaqGroupSchema).optional(),
  })
  .passthrough();

const CreateSchema = z
  .object({
    success: z.literal(true),
  })
  .passthrough();

export type FaqGroup = z.infer<typeof FaqGroupSchema>;

export async function listFaq(): Promise<FaqGroup[]> {
  const res = await apiFetch('/api/cm/faq', { schema: ListSchema });
  return Array.isArray(res.data) ? res.data : [];
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
      language: input.language || 'en',
    }),
  });
}
