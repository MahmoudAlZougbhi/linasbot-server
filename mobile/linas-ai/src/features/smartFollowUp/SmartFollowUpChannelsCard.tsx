import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import {
  CHANNEL_TILES,
  type FollowUpChannelId,
  type FollowUpChannelKey,
  type FollowUpChannelsEnabled,
} from './smartFollowUpOptions';
import { SFU_CARD_BORDER, SFU_TEAL } from './smartFollowUpDesign';

type Props = {
  channels: FollowUpChannelsEnabled;
  disabled?: boolean;
  onToggle: (channel: FollowUpChannelKey) => void;
  onSelectAll: () => void;
};

function isSelected(id: FollowUpChannelId, channels: FollowUpChannelsEnabled): boolean {
  if (id === 'tiktok') return false;
  return Boolean(channels[id]);
}

export function SmartFollowUpChannelsCard({ channels, disabled, onToggle, onSelectAll }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: SFU_CARD_BORDER }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.text }]}>{tr('sfuChannelsTitle')}</Text>
        <Pressable
          onPress={onSelectAll}
          disabled={disabled}
          accessibilityRole="button"
          accessibilityLabel={tr('sfuSelectAll')}
        >
          <Text style={[styles.selectAll, { color: SFU_TEAL }]}>{tr('sfuSelectAll')}</Text>
        </Pressable>
      </View>

      <View style={styles.grid}>
        {CHANNEL_TILES.map((tile) => {
          const selected = isSelected(tile.id, channels);
          const tileDisabled = disabled || !tile.supported;
          return (
            <Pressable
              key={tile.id}
              disabled={tileDisabled}
              onPress={() => {
                if (tile.id !== 'tiktok') onToggle(tile.id);
              }}
              style={[
                styles.tile,
                {
                  borderColor: selected ? SFU_TEAL : SFU_CARD_BORDER,
                  backgroundColor: colors.surface,
                  opacity: tile.supported ? 1 : 0.45,
                },
              ]}
              accessibilityRole="button"
              accessibilityState={{ selected, disabled: tileDisabled }}
              accessibilityLabel={tr(tile.labelKey)}
            >
              {selected ? (
                <View style={[styles.check, { backgroundColor: SFU_TEAL }]}>
                  <Ionicons name="checkmark" size={12} color="#FFFFFF" />
                </View>
              ) : null}
              {tile.iconFamily === 'ion' ? (
                <Ionicons name={tile.iconName as keyof typeof Ionicons.glyphMap} size={28} color={tile.iconColor} />
              ) : (
                <MaterialCommunityIcons
                  name={tile.iconName as keyof typeof MaterialCommunityIcons.glyphMap}
                  size={28}
                  color={tile.iconColor}
                />
              )}
              <Text style={[styles.tileLabel, { color: colors.text }]}>{tr(tile.labelKey)}</Text>
              {!tile.supported ? (
                <Text style={[styles.soon, { color: colors.textMuted }]}>{tr('sfuChannelComingSoon')}</Text>
              ) : null}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
  },
  selectAll: {
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  tile: {
    width: '47%',
    minHeight: 88,
    borderWidth: 1,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    gap: 6,
    position: 'relative',
  },
  check: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tileLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    textAlign: 'center',
  },
  soon: {
    fontFamily: fonts.body,
    fontSize: 11,
  },
});
