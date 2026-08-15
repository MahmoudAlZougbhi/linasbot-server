import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { SideDrawer } from '../../components/SideDrawer';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import type { ControlArea } from '../control/controlAreas';
import { DrawerHeader } from './DrawerHeader';
import { DrawerNavGrid } from './DrawerNavGrid';
import { DrawerRecents } from './DrawerRecents';
import type { HistoryItem } from './HistoryRows';
import { rememberDrawerRecents } from './drawerSessionCache';
import { useDrawerBadges } from './useDrawerBadges';
import { visibleRecentItems } from './visibleRecentItems';

type Props = {
  open: boolean;
  onClose: () => void;
  isAuthenticated: boolean;
  showUsers: boolean;
  activeArea?: ControlArea | 'chat' | null;
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
  const insets = useSafeAreaInsets();
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef<TextInput>(null);
  const badges = useDrawerBadges(props.isAuthenticated, props.open);
  const queryTrimmed = query.trim();
  const searching = searchOpen || queryTrimmed.length > 0;

  useEffect(() => {
    if (!props.open) {
      setSearchOpen(false);
      setQuery('');
      searchRef.current?.blur();
    }
  }, [props.open]);

  useEffect(() => {
    if (!props.isAuthenticated) return;
    rememberDrawerRecents(props.history, props.archivedIds);
  }, [props.isAuthenticated, props.history, props.archivedIds]);

  useEffect(() => {
    if (searchOpen && props.open) {
      const t = setTimeout(() => searchRef.current?.focus(), 40);
      return () => clearTimeout(t);
    }
  }, [searchOpen, props.open]);

  const filtered = useMemo(() => {
    const q = queryTrimmed.toLowerCase();
    const base = visibleRecentItems(props.history, props.archivedIds);
    if (!q) return base;
    return base.filter((h) => (h.title || '').toLowerCase().includes(q));
  }, [props.history, props.archivedIds, queryTrimmed]);

  const emptyLabel = queryTrimmed ? tr('noChatsMatch') : tr('noConversationsYet');

  const closeSearch = () => {
    setSearchOpen(false);
    setQuery('');
    searchRef.current?.blur();
  };

  const openArea = (area: ControlArea) => {
    props.onClose();
    props.onOpenArea(area);
  };

  const confirmDelete = (id: string) => {
    const item = props.history.find((h) => h.id === id);
    Alert.alert(
      tr('deleteConversation'),
      tr('deleteConversationConfirm').replace('{title}', item?.title || tr('untitledChat')),
      [
        { text: tr('usersCancel'), style: 'cancel' },
        {
          text: tr('usersDelete'),
          style: 'destructive',
          onPress: () => props.onDelete(id),
        },
      ],
    );
  };

  const recents = props.isAuthenticated
    ? {
        items: filtered,
        emptyLabel,
        onOpen: (id: string) => {
          props.onOpenChat(id);
          props.onClose();
        },
        onTogglePin: props.onTogglePin,
        onArchive: props.onArchive,
        onUnarchive: props.onUnarchive,
        onRename: props.onRename,
        onDelete: confirmDelete,
      }
    : {
        items: [] as HistoryItem[],
        emptyLabel: tr('signInToKeepHistory'),
        onOpen: () => {},
        onTogglePin: () => {},
        onArchive: () => {},
        onUnarchive: () => {},
        onRename: () => {},
        onDelete: () => {},
      };

  return (
    <SideDrawer
      open={props.open}
      side="left"
      onClose={props.onClose}
      widthRatio={0.88}
      style={{ backgroundColor: colors.drawerSurface, borderColor: colors.borderSoft }}
    >
      <ScrollView
        style={styles.body}
        contentContainerStyle={{ paddingBottom: Math.max(insets.bottom, 8) }}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        showsVerticalScrollIndicator={false}
        removeClippedSubviews={false}
      >
        <DrawerHeader
          searchOpen={searchOpen}
          query={query}
          searchRef={searchRef}
          onOpenSearch={() => setSearchOpen(true)}
          onCloseSearch={closeSearch}
          onChangeQuery={setQuery}
          onOpenSettings={() => openArea('settings')}
        />

        {!searching ? (
          <DrawerNavGrid
            showUsers={props.showUsers}
            activeArea={props.activeArea ?? null}
            badges={badges}
            onOpenArea={openArea}
          />
        ) : null}

        {!props.isAuthenticated ? (
          <View style={styles.guestAuth}>
            <Pressable
              onPress={() => {
                props.onClose();
                props.onLogin?.();
              }}
              style={styles.guestRow}
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
              style={styles.guestRow}
              accessibilityRole="button"
              accessibilityLabel={tr('createAccount')}
            >
              <Text style={{ color: colors.text }}>{tr('createAccount')}</Text>
            </Pressable>
          </View>
        ) : null}

        <DrawerRecents
          items={recents.items}
          pinnedIds={props.isAuthenticated ? props.pinnedIds : []}
          activeId={props.isAuthenticated ? props.activeId : null}
          archivedMode={false}
          emptyLabel={recents.emptyLabel}
          onNewChat={() => {
            props.onClose();
            props.onNewChat();
          }}
          onOpen={recents.onOpen}
          onTogglePin={recents.onTogglePin}
          onArchive={recents.onArchive}
          onUnarchive={recents.onUnarchive}
          onRename={recents.onRename}
          onDelete={recents.onDelete}
        />
      </ScrollView>
    </SideDrawer>
  );
}

const styles = StyleSheet.create({
  body: { flex: 1, minHeight: 0 },
  guestAuth: { gap: 2, marginBottom: spacing.xs },
  guestRow: { minHeight: 36, justifyContent: 'center' },
});
