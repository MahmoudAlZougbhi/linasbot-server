import { StyleSheet, View } from 'react-native';

import { AppIcon, ion, type AppIconName } from '../../components/AppIcon';

export type IntegrationPlatform = 'instagram' | 'facebook' | 'whatsapp' | 'tiktok' | 'web';

const SPEC: Record<IntegrationPlatform, { icon: AppIconName; color: string; bg: string }> = {
  instagram: { icon: ion('logo-instagram'), color: '#E1306C', bg: '#FCE7F3' },
  facebook: { icon: ion('logo-facebook'), color: '#1877F2', bg: '#E8F1FF' },
  whatsapp: { icon: ion('logo-whatsapp'), color: '#25D366', bg: '#E7F8EC' },
  tiktok: { icon: ion('logo-tiktok'), color: '#111111', bg: '#F3F4F6' },
  web: { icon: ion('globe-outline'), color: '#0D9488', bg: '#E6F7F4' },
};

type Props = {
  platform: IntegrationPlatform;
  size?: number;
};

/** Circular brand mark for Integrations cards and the account sheet. */
export function IntegrationPlatformIcon({ platform, size = 48 }: Props) {
  const spec = SPEC[platform] ?? SPEC.instagram;
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
      accessibilityLabel={platform}
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
