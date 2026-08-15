import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, useTheme } from '../../theme';
import { PlatformChannelIcon } from './PlatformChannelIcon';
import type { ChannelFilter, ChatChannel } from './liveChatTypes';

const CHIPS: { id: ChannelFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'whatsapp', label: 'WhatsApp' },
  { id: 'instagram', label: 'Instagram' },
  { id: 'facebook', label: 'Messenger' },
  { id: 'tiktok', label: 'TikTok' },
  { id: 'web', label: 'Website' },
];

type Props = {
  selected: ChannelFilter;
  onSelect: (id: ChannelFilter) => void;
};

export function InboxChannelChips({ selected, onSelect }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <ScrollView
        horizontal
        nestedScrollEnabled
        keyboardShouldPersistTaps="handled"
        showsHorizontalScrollIndicator={false}
        style={styles.scroll}
        contentContainerStyle={styles.row}
        accessibilityRole="tablist"
      >
        {CHIPS.map((chip) => {
          const active = selected === chip.id;
          return (
            <Pressable
              key={chip.id}
              onPress={() => onSelect(chip.id)}
              style={[
                chip.id === 'all' ? styles.chipText : styles.chip,
                {
                  backgroundColor: active ? colors.accentSoft : colors.surface,
                  borderColor: active ? colors.accent : colors.border,
                },
              ]}
              accessibilityRole="tab"
              accessibilityLabel={
                chip.id === 'all' ? tr('reqFilterAll') : `Channel ${chip.label}`
              }
              accessibilityState={{ selected: active }}
            >
              {chip.id === 'all' ? (
                <Text style={[styles.allLabel, { color: colors.text }]}>{tr('reqFilterAll')}</Text>
              ) : (
                <PlatformChannelIcon channel={chip.id as ChatChannel} size={28} />
              )}
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const CHIP_ROW_H = 44;

const styles = StyleSheet.create({
  wrap: { height: CHIP_ROW_H, flexGrow: 0, flexShrink: 0, marginBottom: 8, overflow: 'hidden' },
  scroll: { height: CHIP_ROW_H, flexGrow: 0, flexShrink: 0 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingRight: 8 },
  chip: {
    width: 44,
    height: 44,
    borderRadius: radii.pill,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: {
    minHeight: 44,
    borderRadius: radii.pill,
    borderWidth: 2,
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  allLabel: { fontFamily: fonts.bodyMedium, fontSize: 14 },
});
