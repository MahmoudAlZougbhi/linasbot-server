import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { fetchCmSetupProgress } from '../cm/cmProgressApi';
import { resolveAiSetupTileStatus, type AiSetupTileStatus } from './aiSetupTileStatus';
import { MODULE_ICONS } from './moduleIcons';

type Props = {
  onPress: () => void;
};

export function NavDrawerAiSetupTile({ onPress }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [status, setStatus] = useState<AiSetupTileStatus>('continue');

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const prog = await fetchCmSetupProgress();
        if (cancelled) return;
        const incomplete = prog.summary?.incomplete ?? 0;
        const published = Boolean(prog.summary?.published);
        setStatus(resolveAiSetupTileStatus({ fetchFailed: false, incomplete, published }));
      } catch {
        if (!cancelled) {
          setStatus(resolveAiSetupTileStatus({ fetchFailed: true, incomplete: 0, published: false }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const statusKey =
    status === 'complete'
      ? 'aiSetupStatusComplete'
      : status === 'needs_attention'
        ? 'aiSetupStatusNeedsAttention'
        : 'aiSetupStatusContinue';

  const statusColor =
    status === 'complete' ? colors.mint : status === 'needs_attention' ? colors.warning : colors.accentDeep;

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${tr('navContentManagement')}, ${tr(statusKey)}`}
      style={[
        styles.tile,
        {
          backgroundColor: colors.accentSoft,
          borderColor: colors.accent,
        },
      ]}
    >
      <View style={[styles.glow, { backgroundColor: colors.accentGlow }]} pointerEvents="none" />
      <View style={styles.row}>
        <View style={[styles.iconWrap, { backgroundColor: colors.surface }]}>
          <AppIcon icon={MODULE_ICONS.cm} size={22} color={colors.accentDeep} />
        </View>
        <View style={styles.copy}>
          <Text style={[styles.title, { color: colors.text }]} numberOfLines={1}>
            {tr('navContentManagement')}
          </Text>
          <View style={styles.statusRow}>
            <AppIcon
              icon={
                status === 'complete'
                  ? feather('check-circle')
                  : status === 'needs_attention'
                    ? feather('alert-circle')
                    : feather('play-circle')
              }
              size={14}
              color={statusColor}
            />
            <Text style={[styles.status, { color: statusColor }]} numberOfLines={1}>
              {tr(statusKey)}
            </Text>
          </View>
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tile: {
    width: '100%',
    minHeight: 64,
    borderRadius: radii.md,
    borderWidth: 1.5,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 4,
    overflow: 'hidden',
    justifyContent: 'center',
  },
  glow: {
    position: 'absolute',
    top: -24,
    right: -20,
    width: 120,
    height: 120,
    borderRadius: 60,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 2 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  status: { fontFamily: fonts.body, fontSize: 12, flexShrink: 1 },
});
