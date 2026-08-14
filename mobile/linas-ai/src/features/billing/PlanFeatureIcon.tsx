import { AppIcon, ion, mci, type AppIconName } from '../../components/AppIcon';
import type { FeatureIcon } from './planEntitlements';

const ICONS: Record<FeatureIcon, AppIconName> = {
  chat: ion('chatbubble-ellipses-outline'),
  send: ion('paper-plane-outline'),
  bookmark: ion('bookmark-outline'),
  quotes: mci('comment-quote-outline'),
  person: ion('person-outline'),
  whatsapp: ion('logo-whatsapp'),
  tiktok: ion('logo-tiktok'),
};

export function PlanFeatureIcon({
  name,
  color,
  size = 20,
}: {
  name: FeatureIcon;
  color: string;
  size?: number;
}) {
  return <AppIcon icon={ICONS[name]} size={size} color={color} />;
}
