import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, useTheme } from '../../theme';
import { PlatformChannelIcon } from './PlatformChannelIcon';
import type { ChannelFilter, ChatChannel } from './liveChatTypes';

const CHIPS: { id: ChannelFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'whatsapp', label: 'WhatsApp' },
  { id: 'instagram', label: 'Instagram' },
  { id: 'facebook', label: 'Messenger' },
  { id: 'tiktok', label: 'TikTok' },
];

type Props = {
  selected: ChannelFilter;
  onSelect: (id: ChannelFilter) => void;
};

export function InboxChannelChips({ selected, onSelect }: Props) {
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
                styles.chip,
                {
                  backgroundColor: active ? colors.accentSoft : colors.surface,
                  borderColor: active ? colors.accent : colors.border,
                },
              ]}
              accessibilityRole="tab"
              accessibilityLabel={`Channel ${chip.label}`}
              accessibilityState={{ selected: active }}
            >
              {chip.id !== 'all' ? (
                <View style={styles.icon}>
                  <PlatformChannelIcon channel={chip.id as ChatChannel} size={22} />
                </View>
              ) : null}
              <Text style={[styles.label, { color: active ? colors.text : colors.textMuted }]}>
                {chip.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexGrow: 0, flexShrink: 0, marginBottom: 8 },
  scroll: { flexGrow: 0 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingRight: 8 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 8,
    minHeight: 36,
  },
  icon: { width: 22, height: 22, overflow: 'hidden', borderRadius: 11 },
  label: { fontFamily: fonts.bodyMedium, fontSize: 13 },
});
