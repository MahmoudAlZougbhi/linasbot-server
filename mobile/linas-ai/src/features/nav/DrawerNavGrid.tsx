import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';
import { useI18n } from '../../i18n/LanguageContext';
import type { ThemeColors } from '../../theme';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { ControlArea } from '../control/controlAreas';
import { drawerGridModules } from './drawerModules';
import { drawerTileBadge } from './drawerTileBadge';
import { MODULE_ICONS } from './moduleIcons';
import type { DrawerBadges } from './useDrawerBadges';

type Props = {
  showUsers: boolean;
  activeArea: ControlArea | 'chat' | null;
  badges: DrawerBadges;
  onOpenArea: (area: ControlArea) => void;
};

const GRID_ICON_SIZE = 28;

function DrawerModuleIcon({
  modId,
  colors,
}: {
  modId: ControlArea;
  colors: ThemeColors;
}) {
  if (modId === 'cm') {
    return <LinasSparkleIcon size={GRID_ICON_SIZE} color={colors.accentDeep} />;
  }

  return <AppIcon icon={MODULE_ICONS[modId]} size={GRID_ICON_SIZE} color={colors.accentDeep} />;
}

export function DrawerNavGrid({ showUsers, activeArea, badges, onOpenArea }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const modules = drawerGridModules({ showUsers });

  return (
    <View style={styles.grid}>
      {modules.map((mod) => {
        const badge = drawerTileBadge(mod.id, badges);
        const active = activeArea === mod.id;
        const tileBg = active ? colors.activeRow : 'transparent';

        return (
          <View key={mod.id} style={styles.tileWrap}>
            <Pressable
              style={[styles.tile, { backgroundColor: tileBg }]}
              onPress={() => onOpenArea(mod.id)}
              accessibilityRole="button"
              accessibilityLabel={tr(mod.titleKey)}
            >
              <DrawerModuleIcon modId={mod.id} colors={colors} />
              <Text style={[styles.label, { color: colors.text }]} numberOfLines={2}>
                {tr(mod.titleKey)}
              </Text>
            </Pressable>
            {badge ? (
              <View
                pointerEvents="none"
                style={[
                  styles.badge,
                  badge.tone === 'teal'
                    ? {
                        backgroundColor: colors.accentMid,
                        borderWidth: 1,
                        borderColor: '#FFFFFF',
                      }
                    : { backgroundColor: colors.danger },
                ]}
              >
                <Text
                  style={[
                    styles.badgeText,
                    badge.tone === 'teal' ? { color: '#FFFFFF' } : { color: colors.onAccent },
                  ]}
                >
                  {badge.label}
                </Text>
              </View>
            ) : null}
          </View>
        );
      })}
    </View>
  );
}

const TILE_GAP = 6;

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: TILE_GAP,
    marginBottom: spacing.lg,
    overflow: 'visible',
  },
  tileWrap: {
    width: '31.5%',
    position: 'relative',
    overflow: 'visible',
  },
  tile: {
    width: '100%',
    minHeight: 90,
    borderRadius: radii.md,
    paddingHorizontal: 4,
    paddingVertical: spacing.sm + 2,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    overflow: 'visible',
  },
  badge: {
    position: 'absolute',
    top: -4,
    right: -2,
    zIndex: 4,
    elevation: 4,
    minWidth: 22,
    height: 18,
    borderRadius: radii.pill,
    paddingHorizontal: 5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: { fontFamily: fonts.bodyMedium, fontSize: 10, lineHeight: 12 },
  label: {
    fontFamily: fonts.body,
    fontWeight: '400',
    fontSize: 16,
    lineHeight: 22,
    letterSpacing: -0.15,
    textAlign: 'center',
  },
});
