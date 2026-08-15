import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { radii, useTheme } from '../../theme';
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
              {chip.id === 'all' ? (
                <View
                  style={[
                    styles.allIcon,
                    { backgroundColor: active ? colors.accentSoft : colors.input },
                  ]}
                >
                  <AppIcon icon={feather('globe')} size={16} color={colors.text} />
                </View>
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
  allIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
