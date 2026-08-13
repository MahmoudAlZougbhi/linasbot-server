import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';
import { useI18n } from '../../i18n/LanguageContext';
import type { ThemeColors } from '../../theme';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { ControlArea } from '../control/controlAreas';
import { drawerGridModules, type DrawerModule } from './drawerModules';
import { MODULE_ICONS } from './moduleIcons';
import type { DrawerBadges } from './useDrawerBadges';

type Props = {
  showUsers: boolean;
  activeArea: ControlArea | 'chat' | null;
  badges: DrawerBadges;
  onOpenArea: (area: ControlArea) => void;
};

const GRID_ICON_SIZE = 28;

function badgeForModule(
  mod: DrawerModule,
  badges: DrawerBadges,
): { label: string; tone: 'teal' | 'danger' } | null {
  if (mod.id === 'cm' && badges.aiSetupPercent != null && badges.aiSetupPercent < 100) {
    return { label: `${badges.aiSetupPercent}%`, tone: 'teal' };
  }
  if (mod.id === 'livechat' && badges.liveChatUnread > 0) {
    const n = badges.liveChatUnread > 99 ? '99+' : String(badges.liveChatUnread);
    return { label: n, tone: 'danger' };
  }
  if (mod.id === 'requests' && badges.requestsPending > 0) {
    const n = badges.requestsPending > 99 ? '99+' : String(badges.requestsPending);
    return { label: n, tone: 'danger' };
  }
  return null;
}

function DrawerModuleIcon({
  modId,
  colors,
  active,
}: {
  modId: ControlArea;
  colors: ThemeColors;
  active: boolean;
}) {
  if (modId === 'cm') {
    if (!active) {
      return <LinasSparkleIcon size={GRID_ICON_SIZE} color={colors.accentDeep} />;
    }

    return (
      <View
        style={[
          styles.featuredIconWrap,
          styles.featuredIconShadow,
          {
            backgroundColor: colors.featuredIconBg,
            borderColor: colors.borderSoft,
            shadowColor: colors.text,
          },
        ]}
      >
        <LinasSparkleIcon size={22} color={colors.accentDeep} />
      </View>
    );
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
        const badge = badgeForModule(mod, badges);
        const active = activeArea === mod.id;
        const tileBg = active && mod.id !== 'cm' ? colors.activeRow : 'transparent';

        return (
          <Pressable
            key={mod.id}
            style={[styles.tile, { backgroundColor: tileBg }]}
            onPress={() => onOpenArea(mod.id)}
            accessibilityRole="button"
            accessibilityLabel={tr(mod.titleKey)}
          >
            {badge ? (
              <View
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
            <DrawerModuleIcon modId={mod.id} colors={colors} active={active} />
            <Text style={[styles.label, { color: colors.text }]} numberOfLines={2}>
              {tr(mod.titleKey)}
            </Text>
          </Pressable>
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
  },
  tile: {
    width: '31.5%',
    minHeight: 90,
    borderRadius: radii.md,
    paddingHorizontal: 4,
    paddingVertical: spacing.sm + 2,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    position: 'relative',
  },
  featuredIconWrap: {
    width: 42,
    height: 42,
    borderRadius: 12,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  featuredIconShadow: {
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 6,
    elevation: 2,
  },
  badge: {
    position: 'absolute',
    top: 6,
    right: 6,
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
