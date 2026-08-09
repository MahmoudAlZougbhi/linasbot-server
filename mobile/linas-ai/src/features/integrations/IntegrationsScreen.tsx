import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  AppState,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { z } from 'zod';

import { ApiError, apiFetch } from '../../api/client';
import { tokenStore } from '../../auth/tokenStore';
import { PrimaryButton } from '../../components/PrimaryButton';
import { StatusChip } from '../../components/StatusChip';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, radii, spacing } from '../../theme';
import { AuthGateModal } from '../auth/AuthGateModal';
import { ScreenChrome } from '../shared/ScreenChrome';
import {
  ChannelCapabilityToggles,
  type ChannelToggles,
} from './ChannelCapabilityToggles';

const TogglesSchema = z.object({
  dm: z.boolean(),
  comments: z.boolean(),
});

const RowSchema = z.object({
  platform: z.string(),
  label: z.string(),
  connected: z.boolean(),
  coming_soon: z.boolean().optional(),
  connectable: z.boolean().optional(),
  binding_ids: z.array(z.string()).optional(),
  toggles: TogglesSchema.optional(),
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

function defaultToggles(row: Row): ChannelToggles {
  return row.toggles ?? { dm: false, comments: false };
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
        // Instagram Login may be unconfigured; use Meta Business Login for the same channel.
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
    const previous = defaultToggles(row);
    setBusyToggle({ platform: row.platform, key });
    setError(null);
    setRows((curr) =>
      curr.map((r) =>
        r.platform === row.platform
          ? { ...r, toggles: { ...defaultToggles(r), [key]: value } }
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
        curr.map((r) => (r.platform === row.platform ? { ...r, toggles: res.toggles } : r)),
      );
    } catch (err) {
      setRows((curr) =>
        curr.map((r) => (r.platform === row.platform ? { ...r, toggles: previous } : r)),
      );
      if (err instanceof ApiError && err.status === 401) {
        setAuthGate(true);
      } else if (err instanceof ApiError && err.body && typeof err.body === 'object') {
        const msg = (err.body as { message?: unknown }).message;
        setError(typeof msg === 'string' && msg.trim() ? msg : tr('integrationsToggleError'));
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
      <ScrollView contentContainerStyle={styles.list}>
        {rows.map((row) => {
          const soon = isComingSoon(row);
          const busy = busyPlatform === row.platform;
          const showToggles = !soon && (row.platform === 'instagram' || row.platform === 'facebook');
          return (
            <View key={row.platform} style={styles.card}>
              <View style={styles.head}>
                <Text style={styles.cardTitle}>{platformTitle(row)}</Text>
                {soon ? (
                  <StatusChip label={tr('comingSoon')} tone="soon" />
                ) : (
                  <StatusChip
                    label={row.connected ? tr('connected') : tr('notConnected')}
                    tone={row.connected ? 'ok' : 'neutral'}
                  />
                )}
              </View>
              {soon ? (
                <Text style={styles.soonHint}>{tr('comingSoon')}</Text>
              ) : (
                <>
                  {showToggles ? (
                    <ChannelCapabilityToggles
                      toggles={defaultToggles(row)}
                      busyKey={busyToggle?.platform === row.platform ? busyToggle.key : null}
                      disabled={busyPlatform !== null || busyToggle !== null}
                      onToggle={(key, value) => void setToggle(row, key, value)}
                    />
                  ) : null}
                  {row.connected ? (
                    <PrimaryButton
                      label={tr('disconnect')}
                      onPress={() => void disconnectPlatform(row)}
                      loading={busy}
                      disabled={busyPlatform !== null || busyToggle !== null}
                      variant="danger"
                    />
                  ) : (
                    <PrimaryButton
                      label={tr('connect')}
                      onPress={() =>
                        void connectPlatform(row.platform === 'facebook' ? 'facebook' : 'instagram')
                      }
                      loading={busy}
                      disabled={busyPlatform !== null || busyToggle !== null}
                    />
                  )}
                </>
              )}
            </View>
          );
        })}
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
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderColor: colors.border,
    borderWidth: 1,
    gap: spacing.md,
  },
  head: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardTitle: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 17 },
  soonHint: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
