import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii } from '../../theme';
import { PlatformChannelIcon } from '../livechat/PlatformChannelIcon';
import {
  ACCESS_CHANNELS,
  showsChannelPicker,
  toggleAccessChannel,
} from './usersAccess';
import type { PermissionMap } from './usersPermissions';

type Props = {
  permissions: PermissionMap;
  onChange: (next: PermissionMap) => void;
  disabled?: boolean;
};

export function UserChannelAccess({ permissions, onChange, disabled }: Props) {
  const { tr } = useI18n();
  if (!showsChannelPicker(permissions)) return null;

  return (
    <View style={styles.wrap}>
      <Text style={styles.section}>{tr('usersChannels')}</Text>
      <Text style={styles.sub}>{tr('usersChannelsSub')}</Text>
      <View style={styles.row}>
        {ACCESS_CHANNELS.map((channel) => {
          const on = permissions[channel.key] === true;
          return (
            <Pressable
              key={channel.id}
              onPress={() => onChange(toggleAccessChannel(permissions, channel.key, !on))}
              disabled={disabled}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: on }}
              accessibilityLabel={tr(channel.labelKey)}
              style={[
                styles.chip,
                {
                  backgroundColor: on ? colors.accentSoft : colors.surface,
                  borderColor: on ? colors.accent : colors.border,
                  opacity: disabled ? 0.55 : 1,
                },
              ]}
            >
              <PlatformChannelIcon channel={channel.id} size={22} />
              <Text
                style={[styles.label, { color: colors.text }]}
                numberOfLines={1}
                adjustsFontSizeToFit
                minimumFontScale={0.7}
              >
                {tr(channel.labelKey)}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 16, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.borderSoft },
  section: { fontFamily: fonts.bodyMedium, fontSize: 17, fontWeight: '700', color: colors.text },
  sub: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted, marginTop: 4, marginBottom: 10 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: 10,
    paddingVertical: 8,
    minHeight: 40,
    maxWidth: '100%',
  },
  label: { fontFamily: fonts.bodyMedium, fontSize: 13, maxWidth: 88 },
});
