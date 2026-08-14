import { useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather } from '../../components/AppIcon';
import { GradientBackground } from '../../components/GradientBackground';
import { useI18n } from '../../i18n/LanguageContext';
import { HIT, fonts, spacing, typography, useTheme } from '../../theme';
import { MenuIcon } from '../chat/ChatHeaderIcons';
import { NavDrawer } from '../nav/NavDrawer';
import { useModuleNav } from '../nav/ModuleNavContext';
import { useModuleDrawerHistory } from '../nav/useModuleDrawerHistory';

type Props = {
  title: string;
  subtitle?: string;
  titleColor?: string;
  iconColor?: string;
  centerTitle?: boolean;
  headerRight?: ReactNode;
  /** When set, leading control is a back chevron instead of the hamburger. */
  onBack?: () => void;
  children: ReactNode;
};

/**
 * Module screen chrome: hamburger opens the side drawer.
 * Pass onBack to show a back chevron instead (Choose a plan).
 */
export function ScreenChrome({
  title,
  subtitle,
  titleColor,
  iconColor,
  centerTitle,
  headerRight,
  onBack,
  children,
}: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { tr } = useI18n();
  const nav = useModuleNav();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawer = useModuleDrawerHistory(nav.isAuthenticated, drawerOpen);

  return (
    <GradientBackground>
      <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
        <View style={[styles.headerRow, centerTitle && styles.headerRowCentered]}>
          <Pressable
            onPress={() => (onBack ? onBack() : setDrawerOpen(true))}
            style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
            accessibilityLabel={onBack ? tr('back') : tr('openMenu')}
            accessibilityRole="button"
            hitSlop={4}
          >
            {onBack ? (
              <AppIcon icon={feather('chevron-left')} size={26} color={iconColor ?? colors.text} />
            ) : (
              <MenuIcon color={iconColor ?? colors.text} />
            )}
          </Pressable>
          <View style={[styles.titleBlock, centerTitle && styles.titleBlockCentered]}>
            <Text
              style={[
                centerTitle ? styles.centeredTitle : typography.title,
                { color: titleColor ?? colors.text },
              ]}
              numberOfLines={1}
            >
              {title}
            </Text>
            {subtitle ? (
              <Text
                style={{
                  color: colors.textMuted,
                  fontFamily: fonts.body,
                  marginTop: 4,
                  fontSize: 14,
                  textAlign: centerTitle ? 'center' : 'left',
                }}
              >
                {subtitle}
              </Text>
            ) : null}
          </View>
          {headerRight ? <View style={styles.headerRight}>{headerRight}</View> : <View style={styles.hitSpacer} />}
        </View>
      </View>
      <View style={styles.body}>{children}</View>

      <NavDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        isAuthenticated={nav.isAuthenticated}
        showUsers={nav.isAuthenticated}
        activeArea={nav.activeArea}
        history={drawer.history}
        archivedIds={drawer.archivedIds}
        pinnedIds={drawer.pinnedIds}
        activeId={null}
        workspaceLabel={drawer.workspaceLabel}
        onOpenArea={(area) => {
          setDrawerOpen(false);
          nav.openArea(area);
        }}
        onNewChat={() => {
          setDrawerOpen(false);
          nav.startNewChat();
        }}
        onOpenChat={(id) => {
          setDrawerOpen(false);
          nav.openChat(id);
        }}
        onTogglePin={(id) => void drawer.togglePin(id)}
        onArchive={(id) => void drawer.setArchived(id, true)}
        onUnarchive={(id) => void drawer.setArchived(id, false)}
        onRename={(id, titleNext) => void drawer.rename(id, titleNext)}
        onDelete={(id) => void drawer.remove(id)}
        onLogin={() => {
          setDrawerOpen(false);
          nav.requestLogin();
        }}
        onRegister={() => {
          setDrawerOpen(false);
          nav.requestRegister();
        }}
      />
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  top: { paddingHorizontal: spacing.md, paddingBottom: spacing.md },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  headerRowCentered: {
    alignItems: 'center',
  },
  hit: {
    width: HIT,
    height: HIT,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: -spacing.sm,
  },
  hitSpacer: {
    width: HIT,
    height: HIT,
  },
  headerRight: {
    minWidth: HIT,
    minHeight: HIT,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: -spacing.sm,
  },
  pressed: {
    opacity: 0.55,
  },
  titleBlock: {
    flex: 1,
    paddingTop: 10,
  },
  titleBlockCentered: {
    paddingTop: 0,
    alignItems: 'center',
  },
  centeredTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 17,
    fontWeight: '700',
    textAlign: 'center',
  },
  body: { flex: 1, paddingHorizontal: spacing.lg },
});
