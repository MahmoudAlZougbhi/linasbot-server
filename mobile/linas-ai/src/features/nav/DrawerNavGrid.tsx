import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
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

function DrawerModuleIcon({ modId, colors }: { modId: ControlArea; colors: ThemeColors }) {
  if (modId === 'cm') {
    return (
      <View
        style={[
          styles.featuredIconWrap,
          {
            backgroundColor: colors.surface,
            borderColor: colors.borderSoft,
            shadowColor: colors.accentDeep,
          },
        ]}
      >
        <Text style={[styles.featuredSparkle, { color: colors.accentDeep }]}>✦</Text>
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
        const tileBg = active ? colors.activeRow : 'transparent';

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
                    ? { backgroundColor: colors.accentDeep }
                    : { backgroundColor: colors.danger },
                ]}
              >
                <Text style={[styles.badgeText, { color: colors.onAccent }]}>{badge.label}</Text>
              </View>
            ) : null}
            <DrawerModuleIcon modId={mod.id} colors={colors} />
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
    marginBottom: spacing.md,
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
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.12,
    shadowRadius: 4,
    elevation: 2,
  },
  featuredSparkle: {
    fontSize: 22,
    lineHeight: 24,
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
    fontFamily: fonts.bodyMedium,
    fontSize: 10.5,
    letterSpacing: -0.15,
    textAlign: 'center',
    lineHeight: 13,
  },
});
