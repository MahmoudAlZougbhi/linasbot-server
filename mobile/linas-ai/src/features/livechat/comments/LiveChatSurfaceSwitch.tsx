import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, useTheme } from '../../../theme';

export type LiveChatSurface = 'chats' | 'comments';

type Props = {
  value: LiveChatSurface;
  onChange: (value: LiveChatSurface) => void;
  visible?: LiveChatSurface[];
};

export function LiveChatSurfaceSwitch({ value, onChange, visible }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const tabs = visible ?? (['chats', 'comments'] as const);
  if (tabs.length <= 1) return null;
  return (
    <View
      style={[styles.row, { backgroundColor: colors.surfaceAlt, borderColor: colors.border }]}
      accessibilityRole="tablist"
    >
      {tabs.map((id) => {
        const on = value === id;
        return (
          <Pressable
            key={id}
            onPress={() => onChange(id)}
            style={[styles.chip, on && { backgroundColor: colors.surface, borderColor: colors.accent }]}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            accessibilityLabel={id === 'chats' ? tr('liveChatsTab') : tr('liveCommentsTab')}
          >
            <Text style={[styles.label, { color: on ? colors.text : colors.textMuted }]}>
              {id === 'chats' ? tr('liveChatsTab') : tr('liveCommentsTab')}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: 6,
    padding: 4,
    borderRadius: radii.lg,
    borderWidth: 1,
    marginBottom: 10,
  },
  chip: {
    flex: 1,
    minHeight: 40,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: { fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
});
