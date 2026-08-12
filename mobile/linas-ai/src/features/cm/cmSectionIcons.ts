import { feather, ion, type AppIconName } from '../../components/AppIcon';
import type { CmSectionId } from './cmSections';

/** CM-01 configuration row icons from the mobile design handoff. */
export const CM_SECTION_ICONS: Record<CmSectionId, AppIconName> = {
  ai_basics: feather('book-open'),
  languages: feather('globe'),
  style: ion('color-palette-outline'),
  dynamic_messages: feather('message-square'),
  services: feather('bar-chart-2'),
  branches: feather('map-pin'),
  opening_hours: feather('clock'),
  prices: feather('tag'),
  care: feather('shield'),
  knowledge: feather('book'),
  handoff: feather('user-plus'),
  restricted: feather('slash'),
  comments: feather('message-circle'),
  off_days: feather('calendar'),
  requests_appointments: feather('clipboard'),
  actions: feather('zap'),
  ai_limits: feather('sliders'),
};
