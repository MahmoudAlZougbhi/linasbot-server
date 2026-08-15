import { z } from 'zod';

export const WebChatAppearanceSchema = z.object({
  identity: z.object({
    display_name: z.string(),
    logo_url: z.string(),
    welcome_message: z.string(),
    subtitle: z.string(),
  }),
  theme: z.object({
    mode: z.enum(['light', 'dark']),
    accent_color: z.string(),
  }),
  bubbles: z.object({
    assistant_bg: z.string(),
    assistant_text: z.string(),
    visitor_bg: z.string(),
    visitor_text: z.string(),
  }),
  layout: z.object({
    position: z.enum(['bottom_left', 'bottom_right']),
    size: z.enum(['compact', 'standard', 'large']),
    corners: z.enum(['soft', 'rounded', 'extra_rounded']),
  }),
  launcher: z.object({
    mode: z.enum(['icon', 'icon_text']),
    text: z.string(),
  }),
});

export type WebChatAppearance = z.infer<typeof WebChatAppearanceSchema>;

export type WebChatIntegrationMode = 'linas_widget' | 'custom_chat';
export type WebChatInstallationStatus =
  | 'connected'
  | 'waiting'
  | 'disabled'
  | 'domain_mismatch';
