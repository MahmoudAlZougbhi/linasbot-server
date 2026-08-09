import { useMemo, useRef, useState } from 'react';
import {
  Alert,
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
import { LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import { HIT, fonts, radii, spacing, useTheme } from '../../theme';
import { NewChatIcon } from '../chat/ChatHeaderIcons';
import type { ControlArea } from '../control/controlAreas';
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

export function NavDrawer(props: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [query, setQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const searchRef = useRef<TextInput>(null);
  const modules = visibleDrawerModules({ showUsers: props.showUsers });
  const queryTrimmed = query.trim();

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

  return (
    <SideDrawer open={props.open} side="left" onClose={props.onClose} widthRatio={0.88}>
      <View style={styles.header}>
        <LinasStarMark labeled size={20} />
        <Pressable
          onPress={props.onClose}
          style={[styles.close, { borderColor: colors.border }]}
          accessibilityLabel={tr('closeMenu')}
          accessibilityRole="button"
          hitSlop={4}
        >
          <AppIcon icon={DRAWER_TOOL_ICONS.close} size={18} color={colors.textMuted} />
        </Pressable>
      </View>

      <ScrollView
        style={styles.scrollFlex}
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
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
          style={[styles.searchWrap, { backgroundColor: colors.input, borderColor: colors.border }]}
          onPress={() => searchRef.current?.focus()}
          accessibilityRole="search"
          accessibilityLabel={tr('searchChats')}
        >
          <AppIcon icon={DRAWER_TOOL_ICONS.search} size={16} color={colors.textDim} />
          <TextInput
            ref={searchRef}
            value={query}
            onChangeText={setQuery}
            placeholder={tr('searchChats')}
            placeholderTextColor={colors.textDim}
            style={[styles.search, { color: colors.text }]}
            accessibilityLabel={tr('searchConversationTitles')}
            returnKeyType="search"
            clearButtonMode="while-editing"
            autoCorrect={false}
            autoCapitalize="none"
          />
        </Pressable>

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
        <Pressable
          style={[styles.newChatBtn, { backgroundColor: colors.accent }]}
          onPress={() => {
            props.onNewChat();
            props.onClose();
          }}
          accessibilityRole="button"
          accessibilityLabel={tr('newChat')}
        >
          <NewChatIcon color={colors.onAccent} />
          <Text style={[styles.newChatText, { color: colors.onAccent }]}>{tr('newChat')}</Text>
        </Pressable>

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
  },
  close: {
    width: HIT,
    height: HIT,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    borderWidth: 1,
  },
  scrollFlex: { flex: 1 },
  scroll: { paddingBottom: 16, gap: 8 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tile: {
    width: '47%',
    minHeight: HIT + 12,
    borderRadius: radii.md,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    justifyContent: 'center',
    gap: 8,
  },
  tileText: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  searchWrap: {
    borderWidth: 1,
    borderRadius: radii.md,
    minHeight: HIT,
    paddingHorizontal: 12,
    marginTop: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  search: {
    flex: 1,
    minHeight: HIT - 4,
    paddingVertical: 8,
  },
  archiveToggle: { minHeight: 44, justifyContent: 'center' },
  bottomDock: {
    borderTopWidth: 1,
    paddingTop: spacing.md,
    gap: spacing.sm,
  },
  newChatBtn: {
    minHeight: HIT,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  newChatText: { fontFamily: fonts.bodyMedium, fontWeight: '700' },
  footerRow: {
    minHeight: HIT,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
});
