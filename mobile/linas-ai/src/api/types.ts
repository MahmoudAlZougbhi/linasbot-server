import { z } from 'zod';

export const PublicUserSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  role: z.string(),
  tenantId: z.string().optional(),
  tenant_id: z.string().optional(),
  name: z.string().optional(),
  displayName: z.string().optional(),
  gender: z.enum(['male', 'female', 'unset']).optional(),
  preferredLanguage: z.enum(['ar', 'en', 'fr']).optional(),
  formOfAddress: z.string().optional(),
  status: z.string().optional(),
  permissions: z.record(z.string(), z.boolean()).nullable().optional(),
});

export const MobileLoginResponseSchema = z.object({
  success: z.literal(true),
  user: PublicUserSchema,
  access_token: z.string().min(10),
  refresh_token: z.string().min(10),
  expires_in: z.number().int().positive(),
  token_type: z.literal('Bearer'),
});

export const ConversationSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  created_at: z.number(),
  updated_at: z.number(),
  archived: z.boolean().optional(),
  has_user_message: z.boolean().optional(),
});

export const ChatMessageSchema = z.object({
  id: z.string(),
  role: z.enum(['user', 'assistant', 'system']),
  content: z.string(),
  created_at: z.number(),
  tool_calls: z.array(z.record(z.string(), z.unknown())).nullable().optional(),
  /** Client-only local preview URIs (not persisted by server). */
  local_image_uris: z.array(z.string()).optional(),
});

export type PublicUser = z.infer<typeof PublicUserSchema>;
export type MobileLoginResponse = z.infer<typeof MobileLoginResponseSchema>;
export type ConversationSummary = z.infer<typeof ConversationSummarySchema>;
export type ChatMessage = z.infer<typeof ChatMessageSchema>;
