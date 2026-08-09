import { StyleSheet } from 'react-native';

import { colors, fonts, radii, spacing } from '../../theme';

export const cmFormStyles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.md,
  },
  label: {
    color: colors.textMuted,
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    marginBottom: 6,
  },
  hint: {
    color: colors.textDim,
    fontFamily: fonts.body,
    fontSize: 12,
    lineHeight: 18,
    marginBottom: spacing.md,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSoft,
  },
  rowTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15, flex: 1 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: spacing.md },
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: colors.bgElevated,
  },
  chipOn: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  chipText: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 13 },
  itemCard: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.borderSoft,
  },
  itemTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  itemSub: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12, marginTop: 2 },
  actions: { flexDirection: 'row', gap: 8, marginTop: spacing.md, marginBottom: spacing.xl },
  error: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
  warn: { color: colors.warning, fontFamily: fonts.body, marginBottom: spacing.sm },
  ok: { color: colors.success, fontFamily: fonts.body, marginBottom: spacing.sm },
});
