import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import {
  classifyNotificationsError,
  listOwnerNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type OwnerNotification,
} from './notificationsApi';

export type LiveChatDeepLink = {
  userId: string;
  conversationId: string;
};

type Props = {
  /** Leave the screen when dismissing the auth gate (settings vs chat). */
  onDismissGate?: () => void;
  onOpenLiveChat: (target: LiveChatDeepLink) => void;
  onRequestLogin?: () => void;
  onRequestRegister?: () => void;
  isAuthenticated: boolean;
};

type Gate = 'none' | 'auth' | 'forbidden';

function formatWhen(ts: number | null | undefined, locale: string): string {
  if (!ts) return '';
  try {
    return new Date(ts * 1000).toLocaleString(
      locale.startsWith('ar') ? 'ar' : locale.startsWith('fr') ? 'fr' : 'en',
      {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

function titleFor(n: OwnerNotification, lang: string): string {
  if (lang.startsWith('ar') && n.title_ar) return n.title_ar;
  if (n.title_en) return n.title_en;
  return n.title_ar || n.type;
}

export function NotificationsScreen({
  onDismissGate,
  onOpenLiveChat,
  onRequestLogin,
  onRequestRegister,
  isAuthenticated,
}: Props) {
  const { tr, language } = useI18n();
  const nav = useModuleNav();
  const dismissGate = onDismissGate ?? nav.goChat;
  const [items, setItems] = useState<OwnerNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate>(isAuthenticated ? 'none' : 'auth');

  const load = useCallback(
    async (quiet = false) => {
      if (!isAuthenticated) {
        setGate('auth');
        setLoading(false);
        return;
      }
      if (!quiet) setLoading(true);
      setError(null);
      try {
        const data = await listOwnerNotifications({ limit: 80 });
        setItems(data.notifications);
        setUnread(data.unreadCount);
        setGate('none');
      } catch (err) {
        const kind = classifyNotificationsError(err);
        if (kind === 'auth') {
          setGate('auth');
        } else if (kind === 'forbidden') {
          setGate('forbidden');
        } else {
          setError(tr('notificationsLoadError'));
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [isAuthenticated, tr],
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function onOpen(n: OwnerNotification) {
    if (!n.read) {
      try {
        await markNotificationRead(n.id);
        setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
        setUnread((u) => Math.max(0, u - 1));
      } catch {
        // Still open conversation.
      }
    }
    const userId = n.deep_link?.user_id || n.user_id;
    const conversationId = n.deep_link?.conversation_id || n.conversation_id;
    if (userId && conversationId) {
      onOpenLiveChat({ userId, conversationId });
    }
  }

  async function onMarkAll() {
    try {
      await markAllNotificationsRead();
      setItems((prev) => prev.map((x) => ({ ...x, read: true })));
      setUnread(0);
    } catch {
      setError(tr('notificationsLoadError'));
    }
  }

  if (gate === 'auth') {
    return (
      <ScreenChrome title={tr('notificationsTitle')} subtitle={tr('notificationsSub')}>
        <AuthGateModal
          visible
          reason={tr('notificationsAuthBody')}
          onClose={dismissGate}
          onLogin={() => onRequestLogin?.()}
          onRegister={() => onRequestRegister?.()}
        />
      </ScreenChrome>
    );
  }

  if (gate === 'forbidden') {
    return (
      <ScreenChrome title={tr('notificationsTitle')} subtitle={tr('notificationsSub')}>
        <EmptyState title={tr('notificationsForbiddenTitle')} body={tr('notificationsForbiddenBody')} />
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome title={tr('notificationsTitle')} subtitle={tr('notificationsSub')}>
      {loading ? (
        <ActivityIndicator color={colors.accent} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => {
                setRefreshing(true);
                void load(true);
              }}
              tintColor={colors.accent}
            />
          }
        >
          <View style={styles.metaRow}>
            <Text style={styles.meta}>
              {unread > 0 ? tr('notificationsUnread').replace('{n}', String(unread)) : tr('notificationsAllRead')}
            </Text>
            {unread > 0 ? (
              <Pressable onPress={() => void onMarkAll()}>
                <Text style={styles.markAll}>{tr('notificationsMarkAll')}</Text>
              </Pressable>
            ) : null}
          </View>

          {error ? (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
              <PrimaryButton label={tr('retry')} onPress={() => void load()} />
            </View>
          ) : null}

          {items.length === 0 && !error ? (
            <EmptyState title={tr('notificationsEmptyTitle')} body={tr('notificationsEmptyBody')} />
          ) : null}

          {items.map((n) => (
            <Pressable
              key={n.id}
              style={[styles.row, !n.read && styles.rowUnread]}
              onPress={() => void onOpen(n)}
            >
              <Text style={styles.rowTitle}>{titleFor(n, language)}</Text>
              {n.last_message ? (
                <Text style={styles.rowPreview} numberOfLines={2}>
                  {n.last_message}
                </Text>
              ) : null}
              <Text style={styles.rowWhen}>{formatWhen(n.created_at, language)}</Text>
            </Pressable>
          ))}
        </ScrollView>
      )}
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 40, gap: spacing.sm },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  meta: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 },
  markAll: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 13 },
  errorBox: { gap: spacing.sm, marginBottom: spacing.md },
  errorText: { color: colors.danger, fontFamily: fonts.body },
  row: {
    backgroundColor: colors.bgElevated,
    borderRadius: radii.md,
    padding: spacing.lg - 2,
    borderColor: colors.border,
    borderWidth: 1,
  },
  rowUnread: {
    borderColor: colors.accent,
  },
  rowTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  rowPreview: { color: colors.textMuted, fontFamily: fonts.body, marginTop: 4, fontSize: 13 },
  rowWhen: { color: colors.textDim, fontFamily: fonts.body, marginTop: 6, fontSize: 11 },
});
