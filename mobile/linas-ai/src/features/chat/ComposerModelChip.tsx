import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { modelChipLabel, type OwnerChatMode } from './ownerChatMode';

type Props = {
  mode: OwnerChatMode;
  tappable: boolean;
  open: boolean;
  onOpen: () => void;
};

/** Right-aligned 5.6 LIN chip above the composer pill. */
export function ComposerModelChip({ mode, tappable, open, onOpen }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const label = modelChipLabel(mode);

  return (
    <View style={styles.row}>
      <Pressable
        style={styles.chip}
        onPress={() => {
          if (!tappable) return;
          onOpen();
        }}
        disabled={!tappable}
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityHint={tappable ? tr('composerChooseEffort') : undefined}
        accessibilityState={{ expanded: open }}
      >
        <Text style={[styles.chipText, { color: colors.textMuted }]} numberOfLines={1}>
          {label}
        </Text>
        <AppIcon
          icon={feather(open ? 'chevron-up' : 'chevron-down')}
          size={14}
          color={colors.textMuted}
        />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginBottom: spacing.sm,
    paddingHorizontal: 2,
    direction: 'ltr',
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 2,
    paddingVertical: 2,
    borderRadius: radii.pill,
  },
  chipText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
  },
});
