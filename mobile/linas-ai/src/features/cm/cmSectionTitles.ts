import type { StringKey } from '../../i18n/locales/en';
import type { CmSectionId } from './cmSections';

const TITLE_KEYS: Record<CmSectionId, StringKey> = {
  ai_basics: 'aiSetupSec_ai_basics',
  languages: 'aiSetupSec_languages',
  style: 'aiSetupSec_style',
  dynamic_messages: 'aiSetupSec_dynamic_messages',
  services: 'aiSetupSec_services',
  branches: 'aiSetupSec_branches',
  opening_hours: 'aiSetupSec_opening_hours',
  prices: 'aiSetupSec_prices',
  care: 'aiSetupSec_care',
  knowledge: 'aiSetupSec_knowledge',
  handoff: 'aiSetupSec_handoff',
  restricted: 'aiSetupSec_restricted',
  comments: 'aiSetupSec_comments',
  off_days: 'aiSetupSec_off_days',
  requests_appointments: 'aiSetupSec_requests_appointments',
  ai_limits: 'aiSetupSec_ai_limits',
};

export function cmSectionTitleKey(id: CmSectionId): StringKey {
  return TITLE_KEYS[id];
}
