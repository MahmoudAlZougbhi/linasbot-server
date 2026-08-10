import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { OwnerChatMode } from './ownerChatMode';

type Props = {
  open: boolean;
  mode: OwnerChatMode;
  onClose: () => void;
  onSelect: (mode: OwnerChatMode) => void;
};

function CloudGlyph({ color }: { color: string }) {
  return (
    <View style={cloud.wrap} accessibilityElementsHidden>
      <View style={[cloud.puffL, { backgroundColor: color }]} />
      <View style={[cloud.puffR, { backgroundColor: color }]} />
      <View style={[cloud.base, { backgroundColor: color }]} />
    </View>
  );
}

/** Bottom sheet: Low / High effort (Chat ↔ Low, Work ↔ High). High shows costs-more affordance. */
export function LinEffortSheet({ open, mode, onClose, onSelect }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();

  const rows: { id: OwnerChatMode; title: string; costsMore?: boolean }[] = [
    { id: 'chat', title: tr('linEffortLow') },
    { id: 'work', title: tr('linEffortHigh'), costsMore: true },
  ];

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={[styles.scrim, { backgroundColor: colors.overlay }]} onPress={onClose}>
        <Pressable
          style={[styles.sheet, { backgroundColor: colors.surface, borderColor: colors.border }]}
          onPress={(e) => e.stopPropagation()}
        >
          <Text style={[styles.title, { color: colors.text }]}>{tr('linEffortTitle')}</Text>
          {rows.map((row) => {
            const selected = mode === row.id;
            return (
              <Pressable
                key={row.id}
                style={[
                  styles.row,
                  {
                    backgroundColor: selected ? colors.surfaceAlt : colors.bgElevated,
                    borderColor: selected ? colors.accent : colors.borderSoft,
                  },
                ]}
                onPress={() => {
                  onSelect(row.id);
                  onClose();
                }}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                accessibilityLabel={
                  row.costsMore
                    ? `${row.title}, ${tr('linEffortCostsMore')}`
                    : row.title
                }
              >
                <View style={styles.rowMain}>
                  <Text style={[styles.rowTitle, { color: colors.text }]}>{row.title}</Text>
                  {row.costsMore ? (
                    <View style={styles.costHint}>
                      <CloudGlyph color={colors.textMuted} />
                      <Text style={[styles.costText, { color: colors.textMuted }]}>
                        {tr('linEffortCostsMore')}
                      </Text>
                    </View>
                  ) : null}
                </View>
                {selected ? (
                  <Text style={[styles.check, { color: colors.accent }]}>✓</Text>
                ) : null}
              </Pressable>
            );
          })}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  sheet: {
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    padding: spacing.xl,
    borderTopWidth: 1,
    gap: spacing.sm,
  },
  title: {
    fontFamily: fonts.display,
    fontSize: 18,
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radii.md,
    padding: spacing.lg,
    borderWidth: 1,
  },
  rowMain: { flex: 1, paddingRight: 8, gap: 4 },
  rowTitle: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  costHint: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
  costText: { fontFamily: fonts.body, fontSize: 12 },
  check: { fontFamily: fonts.bodyMedium, fontSize: 16 },
});

const cloud = StyleSheet.create({
  wrap: { width: 18, height: 12, justify: 'relative' },
  base: {
    position: 'absolute',
    left: 1,
    bottom: 0,
    width: 16,
    height: 7,
    borderRadius: 4,
  },
  puffL: {
    position: 'absolute',
    left: 2,
    bottom: 3,
    width: 9,
    height: 9,
    borderRadius: 5,
  },
  puffR: {
    position: 'absolute',
    right: 1,
    bottom: 4,
    width: 7,
    height: 7,
    borderRadius: 4,
  },
});
