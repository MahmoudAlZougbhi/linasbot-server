import { StyleSheet, View } from 'react-native';

import { AppIcon, ion, mci, type AppIconName } from '../../components/AppIcon';
import type { ChatChannel } from './liveChatTypes';

const SPEC: Record<ChatChannel, { icon: AppIconName; color: string; bg: string }> = {
  whatsapp: { icon: ion('logo-whatsapp'), color: '#25D366', bg: '#E7F8EC' },
  instagram: { icon: ion('logo-instagram'), color: '#E1306C', bg: '#FCE7F3' },
  facebook: { icon: mci('facebook-messenger'), color: '#0084FF', bg: '#E8F1FF' },
  tiktok: { icon: ion('logo-tiktok'), color: '#111111', bg: '#F3F4F6' },
};

type Props = {
  channel: ChatChannel;
};

/** Brand-accurate circular platform mark for the Live Chat inbox row. */
export function PlatformChannelIcon({ channel }: Props) {
  const spec = SPEC[channel] ?? SPEC.whatsapp;
  return (
    <View
      style={[styles.wrap, { backgroundColor: spec.bg }]}
      accessibilityLabel={channel}
    >
      <AppIcon icon={spec.icon} size={22} color={spec.color} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
