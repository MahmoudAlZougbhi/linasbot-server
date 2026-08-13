import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
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

export function DrawerNavGrid({ showUsers, activeArea, badges, onOpenArea }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const modules = drawerGridModules({ showUsers });

  return (
    <View style={styles.grid}>
      {modules.map((mod) => {
        const badge = badgeForModule(mod, badges);
        const featured = mod.id === 'cm';
        const active = activeArea === mod.id;
        const tileBg = featured || active ? colors.accentSoft : 'transparent';

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
            <AppIcon icon={MODULE_ICONS[mod.id]} size={22} color={colors.accentDeep} />
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
    minHeight: 88,
    borderRadius: radii.md,
    paddingHorizontal: 4,
    paddingVertical: spacing.sm + 2,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    position: 'relative',
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
    fontSize: 11,
    textAlign: 'center',
    lineHeight: 14,
  },
});
