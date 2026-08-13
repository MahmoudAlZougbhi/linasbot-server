import { Ionicons } from '@expo/vector-icons';
import { StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import type { StringKey } from '../../../i18n/locales/en';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import { formatCount } from '../dashboardFormat';
import type { TenantDashboard } from '../dashboardTypes';

type ChannelRow = NonNullable<TenantDashboard['activity_summary']['channels']>[number];

type Props = {
  channels: ChannelRow[] | undefined;
  unavailable?: boolean;
};

const PLATFORM_LABEL: Record<string, StringKey> = {
  instagram: 'platformInstagram',
  facebook: 'platformFacebook',
  tiktok: 'platformTikTok',
  whatsapp: 'platformWhatsApp',
};

const PLATFORM_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  instagram: 'logo-instagram',
  facebook: 'logo-facebook',
  tiktok: 'logo-tiktok',
  whatsapp: 'logo-whatsapp',
};

const ACTIVE_DOT = '#22C55E';

export function ChannelActivityTable({ channels, unavailable }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const rows = channels ?? [];

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.title, { color: colors.text }]}>{tr('dashActivityByChannel')}</Text>

      <View style={[styles.headerRow, { borderBottomColor: colors.borderSoft }]}>
        <View style={styles.nameCol} />
        <HeaderCell label={tr('dashColMsg')} colors={colors} />
        <HeaderCell label={tr('dashColCom')} colors={colors} />
        <HeaderCell label={tr('dashColSmart')} colors={colors} />
        <HeaderCell label={tr('dashColReq')} colors={colors} />
        <HeaderCell label={tr('dashColCredits')} colors={colors} wide />
      </View>

      {unavailable ? (
        <Text style={{ color: colors.textMuted, fontFamily: fonts.body, padding: spacing.md }}>
          {tr('dashUnavailable')}
        </Text>
      ) : rows.length === 0 ? (
        <Text style={{ color: colors.textMuted, fontFamily: fonts.body, padding: spacing.md }}>
          {tr('dashNoData')}
        </Text>
      ) : (
        rows.map((row) => (
          <View
            key={row.platform}
            style={[styles.dataRow, { borderBottomColor: colors.borderSoft }]}
          >
            <View style={styles.nameCol}>
              <View style={styles.logoWrap}>
                <Ionicons
                  name={PLATFORM_ICON[row.platform] ?? 'globe-outline'}
                  size={22}
                  color={colors.text}
                />
                {row.connected ? <View style={[styles.dot, { backgroundColor: ACTIVE_DOT }]} /> : null}
              </View>
              <Text style={[styles.platformName, { color: colors.text }]} numberOfLines={1}>
                {tr(PLATFORM_LABEL[row.platform] ?? 'platformInstagram')}
              </Text>
            </View>
            <DataCell value={row.messages} colors={colors} />
            <DataCell value={row.comments} colors={colors} />
            <DataCell value={row.smart} colors={colors} />
            <DataCell value={row.requests} colors={colors} />
            <DataCell value={row.credits} colors={colors} wide />
          </View>
        ))
      )}
    </View>
  );
}

function HeaderCell({
  label,
  colors,
  wide,
}: {
  label: string;
  colors: { textDim: string };
  wide?: boolean;
}) {
  return (
    <Text
      style={[styles.headerCell, wide && styles.wideCell, { color: colors.textDim }]}
      numberOfLines={1}
    >
      {label}
    </Text>
  );
}

function DataCell({
  value,
  colors,
  wide,
}: {
  value: number;
  colors: { text: string };
  wide?: boolean;
}) {
  return (
    <Text style={[styles.dataCell, wide && styles.wideCell, { color: colors.text }]}>
      {formatCount(value)}
    </Text>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radii.lg, borderWidth: 1, padding: spacing.lg, gap: spacing.sm },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700', marginBottom: 4 },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: 1,
    paddingBottom: spacing.sm,
  },
  dataRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: 1,
    paddingVertical: spacing.sm + 2,
  },
  nameCol: { flex: 1.35, flexDirection: 'row', alignItems: 'center', gap: spacing.sm, minWidth: 0 },
  logoWrap: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  dot: {
    position: 'absolute',
    right: -1,
    bottom: -1,
    width: 9,
    height: 9,
    borderRadius: 5,
    borderWidth: 1.5,
    borderColor: '#FFFFFF',
  },
  platformName: { fontFamily: fonts.bodyMedium, fontSize: 14, flexShrink: 1 },
  headerCell: {
    flex: 0.55,
    fontFamily: fonts.body,
    fontSize: 11,
    textAlign: 'right',
  },
  dataCell: {
    flex: 0.55,
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    textAlign: 'right',
  },
  wideCell: { flex: 0.75 },
});
