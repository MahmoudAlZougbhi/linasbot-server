import { useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather } from '../../components/AppIcon';
import { GradientBackground } from '../../components/GradientBackground';
import { useI18n } from '../../i18n/LanguageContext';
import { HIT, fonts, spacing, typography, useTheme } from '../../theme';
import { HEADER_HIT, HEADER_ICON_BOX, HeaderMenuButton } from '../chat/ChatHeaderIcons';
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
  /** Extra control immediately after back/menu (e.g. sparkle on Services list). */
  headerLead?: ReactNode;
  /** Hide the title text while keeping back / lead / right alignment. */
  hideTitle?: boolean;
  /** Smaller title on the same row as back (AI Setup nested screens). */
  compactTitle?: boolean;
  /** Settings handoff: title under the hamburger, inset hairline, optional pale canvas. */
  stackedHeader?: boolean;
  /** Section-style title (16px) — Dashboard “Total activity” parity for Settings sub-screens. */
  sectionTitle?: boolean;
  canvasColor?: string;
  /** When set, leading control is a back chevron instead of the hamburger. */
  onBack?: () => void;
  children: ReactNode;
};

/**
 * Module screen chrome: shared silver hamburger opens the side drawer.
 * Pass onBack only for nested steps (Choose a plan from Current plan).
 */
export function ScreenChrome({
  title,
  subtitle,
  titleColor,
  iconColor,
  centerTitle,
  headerRight,
  headerLead,
  hideTitle,
  compactTitle,
  stackedHeader,
  sectionTitle: sectionTitleStyle,
  canvasColor,
  onBack,
  children,
}: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { tr } = useI18n();
  const nav = useModuleNav();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawer = useModuleDrawerHistory(nav.isAuthenticated, drawerOpen);
  const leadColor = iconColor ?? colors.text;
  const compactNav = (compactTitle ?? Boolean(onBack)) && !stackedHeader && !centerTitle;
  const headerTitleStyle = sectionTitleStyle || stackedHeader
    ? typography.sectionTitle
    : compactNav
      ? styles.navTitle
      : typography.title;
  const menu = onBack ? (
    <Pressable
      onPress={onBack}
      style={({ pressed }) => [styles.hit, compactNav && styles.hitCompact, pressed && styles.pressed]}
      accessibilityLabel={tr('back')}
      accessibilityRole="button"
      hitSlop={compactNav ? 10 : 4}
    >
      <AppIcon icon={feather('chevron-left')} size={26} color={leadColor} />
    </Pressable>
  ) : (
    <HeaderMenuButton onPress={() => setDrawerOpen(true)} accessibilityLabel={tr('openMenu')} />
  );

  return (
    <GradientBackground style={canvasColor ? { backgroundColor: canvasColor } : undefined}>
      <View
        style={[
          styles.top,
          stackedHeader && styles.topStacked,
          { paddingTop: insets.top + 8 },
        ]}
      >
        {stackedHeader ? (
          <>
            <View style={styles.menuRow}>{menu}</View>
            <Text
              style={[headerTitleStyle, styles.stackedTitle, { color: titleColor ?? colors.text }]}
              numberOfLines={1}
            >
              {title}
            </Text>
            <View style={[styles.titleRule, { backgroundColor: colors.border }]} />
          </>
        ) : (
          <View
            style={[
              styles.headerRow,
              compactNav && styles.headerRowCompact,
              centerTitle && styles.headerRowCentered,
              Boolean(subtitle) && !centerTitle && styles.headerRowTitleTop,
            ]}
          >
            {menu}
            {headerLead ? <View style={styles.headerLead}>{headerLead}</View> : null}
            <View
              style={[
                styles.titleBlock,
                centerTitle && styles.titleBlockCentered,
                Boolean(subtitle) && !centerTitle && styles.titleBlockWithSub,
                compactNav && Boolean(subtitle) && styles.titleBlockCompactSub,
              ]}
            >
              {hideTitle ? null : (
                <Text
                  style={[
                    centerTitle ? styles.centeredTitle : headerTitleStyle,
                    { color: titleColor ?? colors.text },
                  ]}
                  numberOfLines={1}
                >
                  {title}
                </Text>
              )}
              {subtitle ? (
                <Text
                  style={[
                    styles.subtitle,
                    {
                      color: colors.textMuted,
                      textAlign: centerTitle ? 'center' : 'left',
                    },
                  ]}
                >
                  {subtitle}
                </Text>
              ) : null}
            </View>
            {headerRight ? <View style={styles.headerRight}>{headerRight}</View> : <View style={styles.hitSpacer} />}
          </View>
        )}
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
  topStacked: { paddingHorizontal: 0, paddingBottom: spacing.sm },
  menuRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md },
  stackedTitle: { paddingHorizontal: spacing.lg, marginTop: 2, marginBottom: spacing.sm },
  titleRule: { height: StyleSheet.hairlineWidth, marginHorizontal: spacing.lg },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  headerRowCompact: {
    gap: 2,
  },
  navTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 18,
    lineHeight: 22,
    fontWeight: '700',
  },
  /** Title top matches the silver menu square; subtitle sits under the title only. */
  headerRowTitleTop: {
    alignItems: 'flex-start',
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
  hitCompact: {
    width: 32,
    marginRight: -2,
  },
  hitSpacer: {
    width: HEADER_HIT,
    height: HEADER_HIT,
  },
  headerLead: {
    alignItems: 'center',
    justifyContent: 'center',
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
    justifyContent: 'center',
  },
  titleBlockWithSub: {
    paddingTop: (HEADER_HIT - HEADER_ICON_BOX) / 2,
  },
  titleBlockCompactSub: {
    paddingTop: 13,
  },
  titleBlockCentered: {
    paddingTop: 0,
    alignItems: 'center',
  },
  subtitle: {
    fontFamily: fonts.body,
    marginTop: 4,
    fontSize: 14,
  },
  centeredTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 17,
    fontWeight: '700',
    textAlign: 'center',
  },
  body: { flex: 1, paddingHorizontal: spacing.lg },
});
