import { StyleSheet, Text, View } from 'react-native';

import { AppIcon, ion } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { excludedLabelKey, type ExcludedId } from './planEntitlements';

type Props = {
  ids: ExcludedId[];
  tr: (key: StringKey) => string;
  variant: 'current' | 'choose';
};

export function PlanNotIncluded({ ids, tr, variant }: Props) {
  const { colors } = useTheme();
  if (ids.length === 0) return null;

  if (variant === 'current') {
    return (
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.title, { color: colors.text }]}>{tr('subNotIncluded')}</Text>
        <Text style={[styles.inline, { color: colors.textMuted }]}>
          {ids.map((id) => tr(excludedLabelKey(id))).join(' • ')}
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      <Text style={[styles.title, { color: colors.text }]}>{tr('subNotIncluded')}</Text>
      <View>
        {ids.map((id, index) => (
          <View
            key={id}
            style={[
              styles.row,
              index < ids.length - 1 && {
                borderBottomWidth: StyleSheet.hairlineWidth,
                borderBottomColor: colors.border,
              },
            ]}
          >
            <View style={[styles.xWrap, { borderColor: colors.textDim }]}>
              <AppIcon icon={ion('close')} size={12} color={colors.textDim} />
            </View>
            <Text style={[styles.rowLabel, { color: colors.textMuted }]}>
              {tr(excludedLabelKey(id))}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 4 },
  card: {
    borderRadius: radii.lg,
    borderWidth: 1,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: 6,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  inline: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 12,
  },
  xWrap: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowLabel: { fontFamily: fonts.body, fontSize: 15 },
});
