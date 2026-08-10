import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, AppState, Linking, ScrollView, StyleSheet, Text } from 'react-native';
import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';
import { tokenStore } from '../../auth/tokenStore';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, spacing } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import { ScreenChrome } from '../shared/ScreenChrome';
import {
  IntegrationChannelCard,
  commentsBlocker,
  defaultToggles,
  type IntegrationRow,
} from './IntegrationChannelCard';

const TogglesSchema = z.object({
  dm: z.boolean(),
  comments: z.boolean(),
});

const CommentsStateSchema = z
  .object({
    requested_enabled: z.boolean(),
    permission_present: z.boolean(),
    webhook_subscribed: z.boolean(),
    live_verified: z.boolean(),
    effective_enabled: z.boolean(),
    missing_scopes: z.array(z.string()).optional(),
    blocker: z.string().nullable().optional(),
    status: z.string().optional(),
  })
  .optional();

const RowSchema = z.object({
  platform: z.string(),
  label: z.string(),
  connected: z.boolean(),
  coming_soon: z.boolean().optional(),
  connectable: z.boolean().optional(),
  binding_ids: z.array(z.string()).optional(),
  toggles: TogglesSchema.optional(),
  comments_blocker: z.string().optional(),
  comments_state: CommentsStateSchema,
  capabilities: z.record(z.string(), z.unknown()).optional(),
});

const ListSchema = z.object({
  success: z.literal(true),
  integrations: z.array(RowSchema),
});

const ToggleResponseSchema = z.object({
  success: z.literal(true),
  platform: z.string(),
  toggles: TogglesSchema,
  comments_state: CommentsStateSchema,
});

const StartSchema = z.object({
  success: z.literal(true),
  authorization_url: z.string().url(),
});

const DisconnectSchema = z.object({
  success: z.literal(true),
});

type Row = z.infer<typeof RowSchema>;

type Props = {
  onBack: () => void;
  onRequestLogin?: () => void;
  onRequestRegister?: () => void;
};

const PLATFORM_LABEL: Record<string, StringKey> = {
  instagram: 'platformInstagram',
  facebook: 'platformFacebook',
  tiktok: 'platformTikTok',
  snapchat: 'platformSnapchat',
};

function isComingSoon(row: Row): boolean {
  if (row.coming_soon === true) return true;
  if (row.connectable === false) return true;
  return row.platform === 'tiktok' || row.platform === 'snapchat';
}

export function IntegrationsScreen({ onBack, onRequestLogin, onRequestRegister }: Props) {
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [busyPlatform, setBusyPlatform] = useState<string | null>(null);
  const [busyToggle, setBusyToggle] = useState<{ platform: string; key: 'dm' | 'comments' } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [authGate, setAuthGate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const access = await tokenStore.getAccessToken();
      if (!access) {
        setAuthGate(true);
        setRows([]);
        setError(null);
        return;
      }
      const data = await apiFetch('/api/mobile/integrations', { schema: ListSchema });
      setRows(data.integrations);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAuthGate(true);
        setError(null);
      } else {
        setError(tr('integrationsLoadError'));
      }
    } finally {
      setLoading(false);
    }
  }, [tr]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        void load();
      }
    });
    return () => sub.remove();
  }, [load]);

  async function manageCommentPermissions(platform: 'instagram' | 'facebook') {
    await connectPlatform(platform);
  }

  async function connectPlatform(platform: 'instagram' | 'facebook') {
    setBusyPlatform(platform);
    setError(null);
    try {
      const path =
        platform === 'instagram'
          ? '/api/meta/connections/instagram-login/start'
          : '/api/meta/connections/start';
      const body =
        platform === 'facebook' ? JSON.stringify({ channel: 'facebook' }) : undefined;
      try {
        const started = await apiFetch(path, {
          method: 'POST',
          body,
          schema: StartSchema,
        });
        await Linking.openURL(started.authorization_url);
        return;
      } catch (firstErr) {
        if (platform === 'instagram') {
          const started = await apiFetch('/api/meta/connections/start', {
            method: 'POST',
            body: JSON.stringify({ channel: 'instagram' }),
            schema: StartSchema,
          });
          await Linking.openURL(started.authorization_url);
          return;
        }
        throw firstErr;
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAuthGate(true);
      } else {
        setError(tr('integrationsActionError'));
      }
    } finally {
      setBusyPlatform(null);
    }
  }

  async function disconnectPlatform(row: Row) {
    const ids = row.binding_ids?.filter(Boolean) ?? [];
    if (ids.length === 0) {
      setError(tr('integrationsActionError'));
      return;
    }
    setBusyPlatform(row.platform);
    setError(null);
    try {
      for (const bindingId of ids) {
        await apiFetch(`/api/meta/connections/${encodeURIComponent(bindingId)}/disconnect`, {
          method: 'POST',
          schema: DisconnectSchema,
        });
      }
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setAuthGate(true);
      } else {
        setError(tr('integrationsActionError'));
      }
    } finally {
      setBusyPlatform(null);
    }
  }

  async function setToggle(row: Row, key: 'dm' | 'comments', value: boolean) {
    const previous = defaultToggles(row as IntegrationRow);
    const platform = row.platform === 'facebook' ? 'facebook' : 'instagram';

    if (key === 'comments' && value === true) {
      const blocker = commentsBlocker(row as IntegrationRow);
      if (blocker === 'missing_comment_permissions') {
        const missing = row.comments_state?.missing_scopes?.filter(Boolean) ?? [];
        setError(
          missing.length
            ? `${tr('commentsBlockerMissingPermissions')} Missing: ${missing.join(', ')}.`
            : tr('commentsBlockerMissingPermissions'),
        );
        await manageCommentPermissions(platform);
        return;
      }
      if (blocker === 'connect_channel_first') {
        setError(tr('commentsBlockerConnectFirst'));
        await connectPlatform(platform);
        return;
      }
    }

    setBusyToggle({ platform: row.platform, key });
    setError(null);
    setRows((curr) =>
      curr.map((r) =>
        r.platform === row.platform
          ? { ...r, toggles: { ...defaultToggles(r as IntegrationRow), [key]: value } }
          : r,
      ),
    );
    try {
      const res = await apiFetch(`/api/mobile/integrations/${encodeURIComponent(row.platform)}/toggles`, {
        method: 'PATCH',
        body: JSON.stringify({ [key]: value }),
        schema: ToggleResponseSchema,
      });
      setRows((curr) =>
        curr.map((r) =>
          r.platform === row.platform
            ? {
                ...r,
                toggles: res.toggles,
                comments_state: res.comments_state ?? r.comments_state,
                comments_blocker: res.comments_state?.blocker ?? undefined,
              }
            : r,
        ),
      );
    } catch (err) {
      setRows((curr) =>
        curr.map((r) => (r.platform === row.platform ? { ...r, toggles: previous } : r)),
      );
      if (err instanceof ApiError && err.status === 401) {
        setAuthGate(true);
      } else if (err instanceof ApiError && err.body && typeof err.body === 'object') {
        const body = err.body as {
          message?: unknown;
          error?: unknown;
          reauthorize_required?: unknown;
        };
        const msg = body.message;
        const code = typeof body.error === 'string' ? body.error : '';
        setError(typeof msg === 'string' && msg.trim() ? msg : tr('integrationsToggleError'));
        if (body.reauthorize_required === true || code === 'COMMENT_SCOPES_MISSING') {
          await manageCommentPermissions(platform);
        }
      } else {
        setError(tr('integrationsToggleError'));
      }
    } finally {
      setBusyToggle(null);
    }
  }

  function platformTitle(row: Row): string {
    const key = PLATFORM_LABEL[row.platform];
    return key ? tr(key) : row.label;
  }

  return (
    <ScreenChrome title={tr('integrations')} subtitle={tr('integrationsSub')} onBack={onBack}>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <PrimaryButton
        label={tr('testConnectionReadOnly')}
        onPress={() => void load()}
        loading={loading}
        variant="ghost"
      />
      <Text style={{ color: colors.textMuted, fontSize: 12, marginBottom: spacing.md }}>
        {tr('testConnectionReadOnlyHint')}
      </Text>
      <ScrollView contentContainerStyle={styles.list}>
        {rows
          .filter((row) => row.platform === 'instagram' || row.platform === 'facebook')
          .map((row) => (
            <IntegrationChannelCard
              key={row.platform}
              row={row as IntegrationRow}
              title={platformTitle(row)}
              soon={isComingSoon(row)}
              busy={busyPlatform === row.platform}
              busyToggleKey={busyToggle?.platform === row.platform ? busyToggle.key : null}
              actionsDisabled={busyPlatform !== null || busyToggle !== null}
              tr={tr}
              onToggle={(key, value) => void setToggle(row, key, value)}
              onManageCommentPermissions={() =>
                void manageCommentPermissions(
                  row.platform === 'facebook' ? 'facebook' : 'instagram',
                )
              }
              onConnect={() =>
                void connectPlatform(row.platform === 'facebook' ? 'facebook' : 'instagram')
              }
              onDisconnect={() => void disconnectPlatform(row)}
            />
          ))}
      </ScrollView>

      <AuthGateModal
        visible={authGate}
        onClose={() => {
          setAuthGate(false);
          onBack();
        }}
        onLogin={() => {
          setAuthGate(false);
          onRequestLogin?.();
        }}
        onRegister={() => {
          setAuthGate(false);
          onRequestRegister?.();
        }}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 40, gap: spacing.md },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
