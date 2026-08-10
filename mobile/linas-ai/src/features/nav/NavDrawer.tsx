import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { LinasStarMark } from '../../components/LinasStarMark';
import { SideDrawer } from '../../components/SideDrawer';
import { ANDROID_VERSION_CODE, APP_VERSION, IOS_BUILD, LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { ControlArea } from '../control/controlAreas';
import { NewChatIcon } from '../chat/ChatHeaderIcons';
import { visibleDrawerModules } from './drawerModules';
import { HistoryRows, type HistoryItem } from './HistoryRows';
import { DRAWER_TOOL_ICONS, MODULE_ICONS } from './moduleIcons';

type Props = {
  open: boolean;
  onClose: () => void;
  isAuthenticated: boolean;
  showUsers: boolean;
  history: HistoryItem[];
  archivedIds: string[];
  pinnedIds: string[];
  activeId: string | null;
  workspaceLabel?: string | null;
  onOpenArea: (area: ControlArea) => void;
  onNewChat: () => void;
  onOpenChat: (id: string) => void;
  onTogglePin: (id: string) => void;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onLogin?: () => void;
  onRegister?: () => void;
};

const BUILD_LABEL = Platform.OS === 'ios' ? IOS_BUILD : String(ANDROID_VERSION_CODE);
const VERSION_LABEL = `Linas ${APP_VERSION} · ${BUILD_LABEL}`;

export function NavDrawer(props: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const searchRef = useRef<TextInput>(null);
  const modules = visibleDrawerModules({ showUsers: props.showUsers });
  const queryTrimmed = query.trim();

  useEffect(() => {
    if (!props.open) {
      setSearchOpen(false);
      setQuery('');
      searchRef.current?.blur();
    }
  }, [props.open]);

  useEffect(() => {
    if (searchOpen && props.open) {
      const t = setTimeout(() => searchRef.current?.focus(), 40);
      return () => clearTimeout(t);
    }
  }, [searchOpen, props.open]);

  const filtered = useMemo(() => {
    const q = queryTrimmed.toLowerCase();
    const base = props.history.filter((h) =>
      showArchived ? props.archivedIds.includes(h.id) : !props.archivedIds.includes(h.id),
    );
    if (!q) return base;
    return base.filter((h) => (h.title || '').toLowerCase().includes(q));
  }, [props.history, props.archivedIds, queryTrimmed, showArchived]);

  const emptyLabel = queryTrimmed
    ? tr('noChatsMatch')
    : showArchived
      ? tr('noArchivedChats')
      : tr('noConversationsYet');

  const closeSearch = () => {
    setSearchOpen(false);
    setQuery('');
    searchRef.current?.blur();
  };

  return (
    <SideDrawer open={props.open} side="left" onClose={props.onClose} widthRatio={0.88}>
      <View style={styles.header}>
        {searchOpen ? (
          <View
            style={[
              styles.searchExpanded,
              { backgroundColor: colors.input, borderColor: colors.border },
            ]}
          >
            <AppIcon icon={DRAWER_TOOL_ICONS.search} size={16} color={colors.textDim} />
            <TextInput
              ref={searchRef}
              value={query}
              onChangeText={setQuery}
              placeholder={tr('searchChats')}
              placeholderTextColor={colors.textDim}
              style={[styles.searchInput, { color: colors.text }]}
              accessibilityLabel={tr('searchConversationTitles')}
              returnKeyType="search"
              clearButtonMode="while-editing"
              autoCorrect={false}
              autoCapitalize="none"
            />
            <Pressable
              onPress={closeSearch}
              accessibilityRole="button"
              accessibilityLabel="Close search"
              hitSlop={8}
              style={styles.searchClear}
            >
              <AppIcon icon={DRAWER_TOOL_ICONS.close} size={16} color={colors.textMuted} />
            </Pressable>
          </View>
        ) : (
          <>
            <LinasStarMark labeled size={20} />
            <View style={styles.headerActions}>
              <View style={[styles.headerDivider, { backgroundColor: colors.border }]} />
              <Pressable
                onPress={() => setSearchOpen(true)}
                style={[
                  styles.searchCircle,
                  { borderColor: colors.border, backgroundColor: colors.surface },
                ]}
                accessibilityRole="button"
                accessibilityLabel={tr('searchChats')}
                hitSlop={4}
              >
                <AppIcon icon={DRAWER_TOOL_ICONS.search} size={16} color={colors.accentDeep} />
              </Pressable>
            </View>
          </>
        )}
      </View>

      <ScrollView
        style={styles.scrollFlex}
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        <View style={styles.grid}>
          {modules.map((m) => (
            <Pressable
              key={m.id}
              style={[styles.tile, { backgroundColor: colors.surface, borderColor: colors.border }]}
              onPress={() => {
                props.onClose();
                props.onOpenArea(m.id);
              }}
              accessibilityRole="button"
              accessibilityLabel={m.title}
            >
              <AppIcon icon={MODULE_ICONS[m.id]} size={20} color={colors.accentDeep} />
              <Text style={[styles.tileText, { color: colors.text }]} numberOfLines={2}>
                {m.title}
              </Text>
            </Pressable>
          ))}
        </View>

        <Pressable
          onPress={() => setShowArchived((v) => !v)}
          style={styles.archiveToggle}
          accessibilityRole="button"
          accessibilityLabel={showArchived ? tr('showRecent') : tr('archivedChats')}
        >
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>
            {showArchived ? tr('showRecent') : tr('archivedChats')}
          </Text>
        </Pressable>

        {props.isAuthenticated ? (
          <HistoryRows
            items={filtered}
            pinnedIds={props.pinnedIds}
            activeId={props.activeId}
            archivedMode={showArchived}
            emptyLabel={emptyLabel}
            onOpen={(id) => {
              props.onOpenChat(id);
              props.onClose();
            }}
            onTogglePin={props.onTogglePin}
            onArchive={props.onArchive}
            onUnarchive={props.onUnarchive}
            onRename={props.onRename}
            onDelete={(id) => {
              const item = props.history.find((h) => h.id === id);
              Alert.alert(
                tr('deleteConversation'),
                tr('deleteConversationConfirm').replace(
                  '{title}',
                  item?.title || tr('untitledChat'),
                ),
                [
                  { text: tr('usersCancel'), style: 'cancel' },
                  {
                    text: tr('usersDelete'),
                    style: 'destructive',
                    onPress: () => props.onDelete(id),
                  },
                ],
              );
            }}
          />
        ) : (
          <Text style={{ color: colors.textMuted, marginTop: spacing.md }}>
            {tr('signInToKeepHistory')}
          </Text>
        )}
      </ScrollView>

      <View style={[styles.bottomDock, { borderTopColor: colors.borderSoft }]}>
        <View style={styles.bottomRow}>
          <Pressable
            style={[styles.newChatBtn, { backgroundColor: colors.accent }]}
            onPress={() => {
              props.onNewChat();
              props.onClose();
            }}
            accessibilityRole="button"
            accessibilityLabel={tr('newChat')}
          >
            <NewChatIcon color={colors.onAccent} size={20} />
          </Pressable>
          <Text
            style={[styles.version, { color: colors.textDim }]}
            numberOfLines={1}
            accessibilityRole="text"
            accessibilityLabel={VERSION_LABEL}
          >
            {VERSION_LABEL}
          </Text>
        </View>

        {props.isAuthenticated ? (
          <Text style={{ color: colors.textMuted, fontSize: 12 }} numberOfLines={1}>
            {props.workspaceLabel || tr('workspace')}
          </Text>
        ) : (
          <>
            <Pressable
              onPress={() => {
                props.onClose();
                props.onLogin?.();
              }}
              style={styles.footerRow}
              accessibilityRole="button"
              accessibilityLabel={tr('login')}
            >
              <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>{tr('login')}</Text>
            </Pressable>
            <Pressable
              onPress={() => {
                props.onClose();
                props.onRegister?.();
              }}
              style={styles.footerRow}
              accessibilityRole="button"
              accessibilityLabel={tr('createAccount')}
            >
              <Text style={{ color: colors.text }}>{tr('createAccount')}</Text>
            </Pressable>
            <Text style={{ color: colors.textDim, fontSize: 11 }}>
              {tr('privacy')} · {tr('terms')}
              {LEGAL_URLS.privacy ? '' : ''}
            </Text>
          </>
        )}
      </View>
    </SideDrawer>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
    minHeight: 40,
    gap: spacing.sm,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  headerDivider: {
    width: StyleSheet.hairlineWidth,
    height: 22,
    borderRadius: 1,
  },
  searchCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchExpanded: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderRadius: radii.pill,
    minHeight: 40,
    paddingHorizontal: 12,
  },
  searchInput: {
    flex: 1,
    minHeight: 36,
    paddingVertical: 6,
    fontSize: 15,
  },
  searchClear: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scrollFlex: { flex: 1 },
  scroll: { paddingBottom: 12, gap: 8, flexGrow: 1 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tile: {
    width: '47%',
    minHeight: 52,
    borderRadius: radii.md,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    justifyContent: 'center',
    gap: 8,
  },
  tileText: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  archiveToggle: { minHeight: 40, justifyContent: 'center' },
  bottomDock: {
    borderTopWidth: 1,
    paddingTop: spacing.sm,
    gap: spacing.xs,
  },
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  newChatBtn: {
    width: 36,
    height: 36,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  version: {
    fontFamily: fonts.body,
    fontSize: 11,
    flexShrink: 1,
    textAlign: 'right',
  },
  footerRow: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
});
