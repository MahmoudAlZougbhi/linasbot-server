import { feather, ion, mci, type AppIconName } from '../../components/AppIcon';
import type { CmSectionId } from './cmSections';

/** AI Setup section icons — match mobile design handoff grid. */
export const CM_SECTION_ICONS: Record<CmSectionId, AppIconName> = {
  ai_basics: mci('robot-outline'),
  languages: feather('globe'),
  style: ion('color-palette-outline'),
  dynamic_messages: feather('message-square'),
  services: feather('shopping-bag'),
  branches: feather('map-pin'),
  opening_hours: feather('clock'),
  prices: feather('tag'),
  care: feather('shield'),
  knowledge: feather('book'),
  handoff: feather('user'),
  restricted: ion('ban-outline'),
  comments: feather('message-circle'),
  off_days: feather('calendar'),
  requests_appointments: mci('calendar-check'),
  ai_limits: feather('sliders'),
};
