import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { SideDrawer } from '../../components/SideDrawer';
import { useI18n } from '../../i18n/LanguageContext';
import { spacing, useTheme } from '../../theme';
import type { ControlArea } from '../control/controlAreas';
import { DrawerFooter } from './DrawerFooter';
import { DrawerHeader } from './DrawerHeader';
import { DrawerNavGrid } from './DrawerNavGrid';
import { DrawerRecents } from './DrawerRecents';
import type { HistoryItem } from './HistoryRows';
import { useDrawerBadges } from './useDrawerBadges';

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
    if (searchOpen && props.open) {
      const t = setTimeout(() => searchRef.current?.focus(), 40);
      return () => clearTimeout(t);
    }
  }, [searchOpen, props.open]);

  const filtered = useMemo(() => {
    const q = queryTrimmed.toLowerCase();
    const base = props.history.filter((h) => !props.archivedIds.includes(h.id));
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

  return (
    <SideDrawer
      open={props.open}
      side="left"
      onClose={props.onClose}
      widthRatio={0.88}
      style={{ backgroundColor: colors.drawerSurface, borderColor: colors.borderSoft }}
    >
      <DrawerHeader
        searchOpen={searchOpen}
        query={query}
        searchRef={searchRef}
        onOpenSearch={() => setSearchOpen(true)}
        onCloseSearch={closeSearch}
        onChangeQuery={setQuery}
      />

      <ScrollView
        style={styles.scrollFlex}
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        showsVerticalScrollIndicator={false}
      >
        {!searching ? (
          <DrawerNavGrid
            showUsers={props.showUsers}
            activeArea={props.activeArea ?? null}
            badges={badges}
            onOpenArea={openArea}
          />
        ) : null}

        {props.isAuthenticated ? (
          <DrawerRecents
            items={filtered}
            pinnedIds={props.pinnedIds}
            activeId={props.activeId}
            archivedMode={false}
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
          <View style={{ marginTop: spacing.md }}>
            <DrawerRecents
              items={[]}
              pinnedIds={[]}
              activeId={null}
              archivedMode={false}
              emptyLabel={tr('signInToKeepHistory')}
              onOpen={() => {}}
              onTogglePin={() => {}}
              onArchive={() => {}}
              onUnarchive={() => {}}
              onRename={() => {}}
              onDelete={() => {}}
            />
          </View>
        )}
      </ScrollView>

      <DrawerFooter
        isAuthenticated={props.isAuthenticated}
        onClose={props.onClose}
        onNewChat={props.onNewChat}
        onOpenSettings={() => openArea('settings')}
        onLogin={props.onLogin}
        onRegister={props.onRegister}
      />
    </SideDrawer>
  );
}

const styles = StyleSheet.create({
  scrollFlex: { flex: 1 },
  scroll: { paddingBottom: 8, flexGrow: 1 },
});
