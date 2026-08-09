import { useMemo, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { LinasStarMark } from '../../components/LinasStarMark';
import { SideDrawer } from '../../components/SideDrawer';
import { LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import { HIT, fonts, radii, spacing, useTheme } from '../../theme';
import type { ControlArea } from '../control/controlAreas';
import { visibleDrawerModules } from './drawerModules';
import { HistoryRows, type HistoryItem } from './HistoryRows';

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
  notificationCount?: number;
  onOpenArea: (area: ControlArea) => void;
  onNewChat: () => void;
  onOpenChat: (id: string) => void;
  onTogglePin: (id: string) => void;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onLogout?: () => void;
  onLogin?: () => void;
  onRegister?: () => void;
  onOpenNotifications?: () => void;
};

export function NavDrawer(props: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [query, setQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const modules = visibleDrawerModules({ showUsers: props.showUsers });

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = props.history.filter((h) =>
      showArchived ? props.archivedIds.includes(h.id) : !props.archivedIds.includes(h.id),
    );
    if (!q) return base;
    return base.filter((h) => (h.title || '').toLowerCase().includes(q));
  }, [props.history, props.archivedIds, query, showArchived]);

  return (
    <SideDrawer open={props.open} side="left" onClose={props.onClose} widthRatio={0.88}>
      <View style={styles.header}>
        <LinasStarMark labeled size={20} />
        <Pressable
          onPress={props.onClose}
          style={[styles.close, { borderColor: colors.border }]}
          accessibilityLabel="Close menu"
        >
          <Text style={{ color: colors.textMuted, fontSize: 18 }}>✕</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.grid}>
          {modules.map((m) => (
            <Pressable
              key={m.id}
              style={[styles.tile, { backgroundColor: colors.surface, borderColor: colors.border }]}
              onPress={() => {
                props.onClose();
                props.onOpenArea(m.id);
              }}
              accessibilityLabel={m.title}
            >
              <Text style={[styles.tileText, { color: colors.text }]} numberOfLines={2}>
                {m.title}
              </Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.tools}>
          <Pressable
            style={[styles.toolPrimary, { backgroundColor: colors.accent }]}
            onPress={() => {
              props.onNewChat();
              props.onClose();
            }}
            accessibilityLabel="New chat"
          >
            <Text style={[styles.toolPrimaryText, { color: colors.onAccent }]}>New chat</Text>
          </Pressable>
          <Pressable
            style={[styles.toolSecondary, { backgroundColor: colors.surfaceAlt, borderColor: colors.border }]}
            onPress={() => setShowArchived(false)}
            accessibilityLabel="Search chats"
          >
            <Text style={{ color: colors.text }}>Search</Text>
          </Pressable>
        </View>

        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Search chats"
          placeholderTextColor={colors.textDim}
          style={[
            styles.search,
            { backgroundColor: colors.input, borderColor: colors.border, color: colors.text },
          ]}
          accessibilityLabel="Search conversation titles"
        />

        <Pressable onPress={() => setShowArchived((v) => !v)} style={styles.archiveToggle}>
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>
            {showArchived ? 'Show recent' : 'Archived chats'}
          </Text>
        </Pressable>

        {props.isAuthenticated ? (
          <HistoryRows
            items={filtered}
            pinnedIds={props.pinnedIds}
            activeId={props.activeId}
            archivedMode={showArchived}
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
                'Delete conversation',
                `Delete “${item?.title || 'Untitled'}”? This cannot be undone.`,
                [
                  { text: 'Cancel', style: 'cancel' },
                  { text: 'Delete', style: 'destructive', onPress: () => props.onDelete(id) },
                ],
              );
            }}
          />
        ) : (
          <Text style={{ color: colors.textMuted, marginTop: spacing.md }}>
            Sign in to keep Owner Copilot history. Guest chats stay on this device session only.
          </Text>
        )}
      </ScrollView>

      <View style={[styles.footer, { borderTopColor: colors.borderSoft }]}>
        {props.isAuthenticated ? (
          <>
            <Text style={{ color: colors.textMuted, fontSize: 12 }} numberOfLines={1}>
              {props.workspaceLabel || 'Workspace'}
            </Text>
            {props.onOpenNotifications ? (
              <Pressable
                onPress={() => {
                  props.onClose();
                  props.onOpenNotifications?.();
                }}
                style={styles.footerRow}
                accessibilityLabel="Notifications"
              >
                <Text style={{ color: colors.text }}>Notifications</Text>
                {props.notificationCount ? (
                  <View style={[styles.badge, { backgroundColor: colors.accent }]}>
                    <Text style={{ color: colors.onAccent, fontSize: 11 }}>
                      {props.notificationCount}
                    </Text>
                  </View>
                ) : null}
              </Pressable>
            ) : null}
            <Pressable
              onPress={() => {
                props.onClose();
                props.onLogout?.();
              }}
              style={styles.footerRow}
              accessibilityLabel={tr('logout')}
            >
              <Text style={{ color: colors.danger, fontFamily: fonts.bodyMedium }}>Log out</Text>
            </Pressable>
          </>
        ) : (
          <>
            <Pressable
              onPress={() => {
                props.onClose();
                props.onLogin?.();
              }}
              style={styles.footerRow}
            >
              <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>Log in</Text>
            </Pressable>
            <Pressable
              onPress={() => {
                props.onClose();
                props.onRegister?.();
              }}
              style={styles.footerRow}
            >
              <Text style={{ color: colors.text }}>Create account</Text>
            </Pressable>
            <Text style={{ color: colors.textDim, fontSize: 11 }}>
              Privacy · Terms available in Settings after sign-in ({LEGAL_URLS.privacy ? 'linked' : ''})
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
  scroll: { paddingBottom: 24, gap: 8 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tile: {
    width: '47%',
    minHeight: HIT + 8,
    borderRadius: radii.md,
    borderWidth: 1,
    padding: spacing.md,
    justifyContent: 'center',
  },
  tileText: { fontFamily: fonts.bodyMedium, fontSize: 13 },
  tools: { flexDirection: 'row', gap: 8, marginTop: spacing.sm },
  toolPrimary: {
    flex: 1,
    minHeight: HIT,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  toolPrimaryText: { fontFamily: fonts.bodyMedium, fontWeight: '700' },
  toolSecondary: {
    flex: 1,
    minHeight: HIT,
    borderRadius: radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  search: {
    borderWidth: 1,
    borderRadius: radii.md,
    minHeight: HIT,
    paddingHorizontal: 12,
    marginTop: 4,
  },
  archiveToggle: { minHeight: 40, justifyContent: 'center' },
  footer: {
    borderTopWidth: 1,
    paddingTop: spacing.md,
    gap: 4,
  },
  footerRow: {
    minHeight: HIT,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  badge: {
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
});
