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
  size?: number;
};

/** Brand-accurate circular platform mark for inbox rows and request cards. */
export function PlatformChannelIcon({ channel, size = 48 }: Props) {
  const spec = SPEC[channel] ?? SPEC.whatsapp;
  return (
    <View
      style={[
        styles.wrap,
        {
          backgroundColor: spec.bg,
          width: size,
          height: size,
          borderRadius: size / 2,
        },
      ]}
      accessibilityLabel={channel}
    >
      <AppIcon icon={spec.icon} size={Math.round(size * 0.46)} color={spec.color} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
