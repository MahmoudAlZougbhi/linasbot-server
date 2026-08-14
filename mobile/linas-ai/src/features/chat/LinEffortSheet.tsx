import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { OWNER_LIN_DISPLAY, type OwnerChatMode } from './ownerChatMode';

type Props = {
  open: boolean;
  mode: OwnerChatMode;
  onClose: () => void;
  onSelect: (mode: OwnerChatMode) => void;
};

/** Floating card: 5.6 LIN Low / High with Fast / More powerful. */
export function LinEffortSheet({ open, mode, onClose, onSelect }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();

  const rows: {
    id: OwnerChatMode;
    title: string;
    sub: string;
    trailing: 'check' | 'bolt';
  }[] = [
    {
      id: 'chat',
      title: `${OWNER_LIN_DISPLAY} ${tr('linEffortLow')}`,
      sub: tr('linEffortFast'),
      trailing: 'check',
    },
    {
      id: 'work',
      title: `${OWNER_LIN_DISPLAY} ${tr('linEffortHigh')}`,
      sub: tr('linEffortHighSub'),
      trailing: 'bolt',
    },
  ];

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose}>
        <View style={styles.anchor} pointerEvents="box-none">
          <Pressable
            style={[
              styles.menu,
              {
                backgroundColor: colors.surface,
                borderColor: colors.borderSoft,
                shadowColor: colors.text,
              },
            ]}
            onPress={(e) => e.stopPropagation()}
          >
            {rows.map((row, index) => {
              const selected = mode === row.id;
              return (
                <View key={row.id}>
                  {index > 0 ? (
                    <View style={[styles.divider, { backgroundColor: colors.borderSoft }]} />
                  ) : null}
                  <Pressable
                    style={styles.row}
                    onPress={() => {
                      onSelect(row.id);
                      onClose();
                    }}
                    accessibilityRole="button"
                    accessibilityState={{ selected }}
                    accessibilityLabel={`${row.title}, ${row.sub}`}
                  >
                    <View style={styles.rowMain}>
                      <Text style={[styles.rowTitle, { color: colors.text }]}>{row.title}</Text>
                      <Text style={[styles.rowSub, { color: colors.textDim }]}>{row.sub}</Text>
                    </View>
                    {selected ? (
                      <AppIcon icon={feather('check')} size={18} color={colors.accent} />
                    ) : row.trailing === 'bolt' ? (
                      <AppIcon icon={feather('zap')} size={18} color={colors.accent} />
                    ) : null}
                  </Pressable>
                </View>
              );
            })}
          </Pressable>
        </View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: 'transparent',
    justifyContent: 'flex-end',
  },
  anchor: {
    alignItems: 'flex-end',
    paddingHorizontal: spacing.md,
    paddingBottom: 132,
    direction: 'ltr',
  },
  menu: {
    minWidth: 248,
    borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    paddingVertical: 4,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 12,
    elevation: 8,
    direction: 'ltr',
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    marginHorizontal: spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    gap: spacing.sm,
  },
  rowMain: { flex: 1, gap: 2 },
  rowTitle: { fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  rowSub: { fontFamily: fonts.body, fontSize: 12, lineHeight: 16 },
});
