import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';

export type PlusAction =
  | 'attach_image'
  | 'attach_document'
  | 'add_cm'
  | 'review_setup'
  | 'check_usage';

type Props = {
  open: boolean;
  onClose: () => void;
  onAction: (action: PlusAction) => void;
};

function PhotosGlyph({ color }: { color: string }) {
  return (
    <View style={glyph.box}>
      <View style={[glyph.frame, { borderColor: color }]} />
      <View style={[glyph.peakL, { borderBottomColor: color }]} />
      <View style={[glyph.peakR, { borderBottomColor: color }]} />
      <View style={[glyph.sun, { borderColor: color }]} />
    </View>
  );
}

function PaperclipGlyph({ color }: { color: string }) {
  return (
    <View style={glyph.clipWrap}>
      <View style={[glyph.clipOuter, { borderColor: color }]} />
      <View style={[glyph.clipInner, { borderColor: color }]} />
    </View>
  );
}

/** Plus menu: circular Photos + Files icons matching design. */
export function ComposerPlusSheet({ open, onClose, onAction }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();

  const primary: { id: PlusAction; title: string; Glyph: typeof PhotosGlyph }[] = [
    { id: 'attach_image', title: tr('photos'), Glyph: PhotosGlyph },
    { id: 'attach_document', title: tr('files'), Glyph: PaperclipGlyph },
  ];

  const secondary: { id: PlusAction; title: string; subtitle: string }[] = [
    { id: 'add_cm', title: tr('addEditCm'), subtitle: 'Content Management' },
    { id: 'review_setup', title: tr('reviewSetup'), subtitle: 'CM readiness' },
    { id: 'check_usage', title: tr('checkUsage'), subtitle: 'Credits & wallet' },
  ];

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={[styles.scrim, { backgroundColor: colors.overlay }]} onPress={onClose}>
        <Pressable
          style={[styles.sheet, { backgroundColor: colors.surface, borderColor: colors.border }]}
          onPress={(e) => e.stopPropagation()}
        >
          <Text style={[styles.title, { color: colors.text }]}>{tr('addToChat')}</Text>
          <View style={styles.iconRow}>
            {primary.map((a) => (
              <Pressable
                key={a.id}
                style={styles.iconCol}
                onPress={() => {
                  onAction(a.id);
                  onClose();
                }}
                accessibilityLabel={a.title}
                accessibilityRole="button"
              >
                <View style={[styles.circle, { backgroundColor: colors.surfaceAlt }]}>
                  <a.Glyph color={colors.text} />
                </View>
                <Text style={[styles.iconLabel, { color: colors.text }]}>{a.title}</Text>
              </Pressable>
            ))}
          </View>
          {secondary.map((a) => (
            <Pressable
              key={a.id}
              style={[
                styles.row,
                { backgroundColor: colors.bgElevated, borderColor: colors.borderSoft },
              ]}
              onPress={() => {
                onAction(a.id);
                onClose();
              }}
            >
              <View style={styles.rowText}>
                <Text style={[styles.rowTitle, { color: colors.text }]}>{a.title}</Text>
                <Text style={[styles.rowSub, { color: colors.textMuted }]}>{a.subtitle}</Text>
              </View>
            </Pressable>
          ))}
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
  iconRow: {
    flexDirection: 'row',
    gap: spacing.xl,
    marginBottom: spacing.md,
    paddingHorizontal: spacing.sm,
  },
  iconCol: {
    alignItems: 'center',
    gap: 8,
  },
  circle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radii.md,
    padding: spacing.lg,
    borderWidth: 1,
  },
  rowText: { flex: 1, paddingRight: 8 },
  rowTitle: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  rowSub: { fontFamily: fonts.body, fontSize: 12, marginTop: 2 },
});

const glyph = StyleSheet.create({
  box: { width: 24, height: 24 },
  frame: {
    position: 'absolute',
    left: 1,
    top: 3,
    width: 22,
    height: 18,
    borderWidth: 1.8,
    borderRadius: 4,
  },
  peakL: {
    position: 'absolute',
    left: 4,
    bottom: 5,
    width: 0,
    height: 0,
    borderLeftWidth: 5,
    borderRightWidth: 5,
    borderBottomWidth: 8,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
  },
  peakR: {
    position: 'absolute',
    left: 11,
    bottom: 5,
    width: 0,
    height: 0,
    borderLeftWidth: 6,
    borderRightWidth: 6,
    borderBottomWidth: 10,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
  },
  sun: {
    position: 'absolute',
    right: 5,
    top: 6,
    width: 5,
    height: 5,
    borderRadius: 2.5,
    borderWidth: 1.5,
  },
  clipWrap: { width: 22, height: 24, alignItems: 'center', justifyContent: 'center' },
  clipOuter: {
    width: 10,
    height: 18,
    borderWidth: 1.8,
    borderRadius: 5,
  },
  clipInner: {
    position: 'absolute',
    width: 6,
    height: 12,
    borderWidth: 1.8,
    borderRadius: 3,
    top: 4,
  },
});
