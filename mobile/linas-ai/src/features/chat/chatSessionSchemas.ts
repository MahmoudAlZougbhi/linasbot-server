import { z } from 'zod';

import { ChatMessageSchema, ConversationSummarySchema } from '../../api/types';

export const CreateConvSchema = z.object({
  success: z.literal(true),
  conversation: z.object({
    id: z.string(),
    title: z.string(),
    messages: z.array(ChatMessageSchema),
    setup_stage: z.string().optional(),
    greeting_language: z.string().optional(),
    welcome_chips: z
      .array(
        z.object({
          id: z.string(),
          label: z.string(),
          mode: z.enum(['chat', 'work']),
          prompt: z.string(),
        }),
      )
      .optional(),
  }),
});

export const GetConvSchema = z.object({
  success: z.literal(true),
  conversation: z.object({
    id: z.string(),
    title: z.string(),
    messages: z.array(ChatMessageSchema),
    has_more: z.boolean().optional(),
    total_messages: z.number().optional(),
  }),
});

export const ListConvSchema = z.object({
  success: z.literal(true),
  conversations: z.array(ConversationSummarySchema),
});

const ProposedPatchSchema = z
  .object({
    proposal_id: z.string().optional(),
    confirmation_token: z.string().optional(),
    preview: z.record(z.string(), z.unknown()).optional(),
  })
  .nullable()
  .optional();

export const SendSchema = z.object({
  success: z.literal(true),
  message: ChatMessageSchema.nullable(),
  pending_confirmation: z.string().nullable().optional(),
  proposed_patch: ProposedPatchSchema,
  quick_actions: z.array(z.object({ id: z.string(), label: z.string() })).optional(),
  setup_stage: z.string().nullable().optional(),
});

export type ProposedPatch = {
  proposal_id?: string;
  confirmation_token?: string;
  preview?: Record<string, unknown>;
};

/** @deprecated Creative Studio cancelled — type retained only so dead UI files typecheck. */
export type CreativeDraft = {
  status?: string;
  kind?: string;
  text?: string;
  prompt?: string;
  reason?: string;
  job_id?: string;
  model?: string;
  task_options?: { id: string; label: string }[];
  actions?: {
    edit?: boolean;
    regenerate?: boolean;
    schedule?: boolean;
    publish?: boolean;
    publish_reason?: string;
  };
};
