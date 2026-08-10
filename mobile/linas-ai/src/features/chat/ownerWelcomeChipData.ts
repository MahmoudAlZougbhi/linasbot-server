import type { StringKey } from '../../i18n/locales/en';
import type { OwnerChatMode } from './ownerChatMode';

export type OwnerWelcomeChipDef = {
  id: string;
  labelKey: StringKey;
  mode: OwnerChatMode;
  prompt: string;
};

/** Mirrors server `services/owner_ai_onboarding.py` welcome chips (labels via i18n). */
export const OWNER_WELCOME_CHIPS: OwnerWelcomeChipDef[] = [
  {
    id: 'learn_app',
    labelKey: 'welcomeChipLearnApp',
    mode: 'chat',
    prompt:
      'Give me a clear tour of what Linas AI can do for my business: ' +
      'Owner Copilot, Content Management (the AI that replies to customers), ' +
      'Meta DMs/comments, subscription/usage. Keep it simple and actionable.',
  },
  {
    id: 'setup_guided',
    labelKey: 'welcomeChipSetupGuided',
    mode: 'work',
    prompt:
      'I want to set up the AI that replies to my customers (Content Management) ' +
      'in guided mode — one section at a time. ' +
      'Call cm_fill_plan action=start, skip DONE/filled sections, ' +
      'then work ONLY plan.focus with inspect_cm_guide and propose_cm_patch. ' +
      'Ask me the next question now.',
  },
  {
    id: 'setup_bulk',
    labelKey: 'welcomeChipSetupBulk',
    mode: 'work',
    prompt:
      'I want bulk CM setup. Ask me for a complete business description and how I want ' +
      'the AI to reply (I may paste text and/or attach a file). ' +
      'When I provide it, call ingest_business_dump to distribute into CM sections, ' +
      'then propose the first section for approval and continue after each approve.',
  },
  {
    id: 'connect_meta',
    labelKey: 'welcomeChipConnectMeta',
    mode: 'work',
    prompt:
      'Help me connect Instagram/Facebook for customer DMs and comments. ' +
      'Use read_integrations / diagnose_meta_health. Do not disconnect or rotate tokens.',
  },
  {
    id: 'check_plan',
    labelKey: 'welcomeChipCheckPlan',
    mode: 'chat',
    prompt:
      'Check my subscription and plan entitlements with read_subscription. Explain clearly what I have.',
  },
];
