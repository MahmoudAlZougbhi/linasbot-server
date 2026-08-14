import { StyleSheet } from 'react-native';

import { colors, fonts, radii, spacing } from '../../theme';

export const chatScreenStyles = StyleSheet.create({
  flex: { flex: 1 },
  ltr: { direction: 'ltr' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  list: { padding: 16, paddingBottom: 28, flexGrow: 1 },
  error: {
    color: colors.danger,
    fontFamily: fonts.body,
    paddingHorizontal: 16,
    paddingTop: 8,
  },
  gate: {
    color: colors.warning,
    fontFamily: fonts.body,
    paddingHorizontal: 16,
    paddingTop: 6,
    fontSize: 13,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingHorizontal: 14,
    marginBottom: 8,
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgElevated,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  chipText: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 12 },
  patchCard: {
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    padding: spacing.md,
    borderColor: colors.accent,
    borderWidth: 1,
    gap: 8,
  },
  patchTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 14 },
  patchBody: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
  patchActions: { flexDirection: 'row', gap: 8 },
  confirm: {
    flex: 1,
    backgroundColor: colors.accentSoft,
    borderRadius: 14,
    padding: 12,
    borderColor: colors.accent,
    borderWidth: 1,
  },
  confirmText: {
    color: colors.accent,
    fontFamily: fonts.bodyMedium,
    fontWeight: '700',
    textAlign: 'center',
  },
  reject: {
    flex: 1,
    borderRadius: 14,
    padding: 12,
    borderColor: colors.border,
    borderWidth: 1,
  },
  rejectText: {
    color: colors.textMuted,
    fontFamily: fonts.bodyMedium,
    textAlign: 'center',
  },
});
