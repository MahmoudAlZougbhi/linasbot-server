import { useCallback, useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { IntegrationCardShell } from './IntegrationCardShell';
import {
  fetchWebChatSettings,
  rotateWebChatKey,
  saveWebChatSettings,
  type WebChatSettings,
} from './webChatApi';

type Props = {
  onError?: (message: string) => void;
  onNotice?: (message: string) => void;
};

export function WebChatCard({ onError, onNotice }: Props) {
  const { tr } = useI18n();
  const [settings, setSettings] = useState<WebChatSettings | null>(null);
  const [siteUrl, setSiteUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchWebChatSettings();
      setSettings(data);
      setSiteUrl(data.site_url || '');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      onError?.(tr('integrationsActionError'));
    } finally {
      setLoading(false);
    }
  }, [onError, tr]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(enabled?: boolean) {
    if (!settings?.membership_allows) {
      onError?.(settings?.membership_message || tr('webChatPlanRequired'));
      return;
    }
    setBusy(true);
    try {
      const data = await saveWebChatSettings({
        site_url: siteUrl.trim(),
        enabled: enabled ?? settings?.enabled,
      });
      setSettings(data);
      setSiteUrl(data.site_url || '');
      onNotice?.(tr('webChatSaved'));
    } catch (err) {
      if (err instanceof ApiError && err.body && typeof err.body === 'object') {
        const body = err.body as { message?: unknown };
        const msg = typeof body.message === 'string' ? body.message : tr('integrationsActionError');
        onError?.(msg);
      } else {
        onError?.(tr('integrationsActionError'));
      }
    } finally {
      setBusy(false);
    }
  }

  async function copyEmbed() {
    if (!settings?.embed_snippet) return;
    await Clipboard.setStringAsync(settings.embed_snippet);
    onNotice?.(tr('webChatEmbedCopied'));
  }

  async function onRotateKey() {
    Alert.alert(tr('webChatRotateKey'), tr('webChatRotateKeyConfirm'), [
      { text: tr('usersCancel'), style: 'cancel' },
      {
        text: tr('webChatRotateKeyAction'),
        style: 'destructive',
        onPress: () => {
          void (async () => {
            setBusy(true);
            try {
              const data = await rotateWebChatKey();
              setSettings(data);
              onNotice?.(tr('webChatKeyRotated'));
            } catch {
              onError?.(tr('integrationsActionError'));
            } finally {
              setBusy(false);
            }
          })();
        },
      },
    ]);
  }

  const connected = Boolean(settings?.connected);
  const operational = Boolean(settings?.operational);
  const planBlocked = settings?.membership_allows === false;

  return (
    <View accessibilityRole="summary" style={styles.wrap}>
      <IntegrationCardShell
        platform="web"
        title={tr('platformWeb')}
        subtitle={connected ? siteUrl || tr('platformWeb') : tr('webChatSubtitle')}
        connected={connected}
        busy={busy || loading}
        connectLabel={tr('webChatEnable')}
        connectedLabel={tr('connected')}
        notConnectedLabel={tr('notConnected')}
        comingSoonLabel={tr('comingSoon')}
        healthLabel={operational ? tr('integrationStatusConnected') : tr('notConnected')}
        showConnect={!connected && !planBlocked}
        showMenu={connected}
        showHealth={operational}
        onConnect={() => void save(true)}
        onMenu={onRotateKey}
      >
        {planBlocked ? <Text style={styles.warn}>{tr('webChatPlanRequired')}</Text> : null}
        {!planBlocked ? (
          <>
            <Text style={styles.label}>{tr('webChatSiteUrl')}</Text>
            <TextInput
              value={siteUrl}
              onChangeText={setSiteUrl}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              placeholder="https://yourbusiness.com"
              placeholderTextColor={colors.textMuted}
              style={styles.input}
              editable={!busy}
            />
            <View style={styles.row}>
              <Pressable
                disabled={busy}
                onPress={() => void save()}
                style={[styles.btn, { backgroundColor: colors.accent }]}
              >
                <Text style={styles.btnText}>{tr('webChatSave')}</Text>
              </Pressable>
              {settings?.enabled ? (
                <Pressable disabled={busy} onPress={() => void save(false)} style={styles.linkBtn}>
                  <Text style={styles.linkText}>{tr('webChatDisable')}</Text>
                </Pressable>
              ) : null}
            </View>
            {settings?.embed_snippet ? (
              <>
                <Text style={styles.label}>{tr('webChatEmbedTitle')}</Text>
                <Text selectable style={styles.code}>
                  {settings.embed_snippet}
                </Text>
                <Pressable disabled={busy} onPress={() => void copyEmbed()} style={styles.linkBtn}>
                  <Text style={styles.linkText}>{tr('webChatCopyEmbed')}</Text>
                </Pressable>
              </>
            ) : null}
          </>
        ) : null}
      </IntegrationCardShell>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: spacing.md },
  warn: { fontFamily: fonts.body, fontSize: 13, color: colors.warning, marginBottom: spacing.sm },
  label: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.text, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 10,
    fontFamily: fonts.body,
    fontSize: 14,
    color: colors.text,
    marginBottom: spacing.sm,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginBottom: spacing.sm },
  btn: { borderRadius: radii.sm, paddingHorizontal: spacing.md, paddingVertical: 10 },
  btnText: { fontFamily: fonts.bodyMedium, color: '#fff', fontSize: 14 },
  linkBtn: { paddingVertical: 6 },
  linkText: { fontFamily: fonts.bodyMedium, color: colors.accent, fontSize: 14 },
  code: {
    fontFamily: fonts.body,
    fontSize: 12,
    color: colors.textMuted,
    backgroundColor: colors.input,
    padding: spacing.sm,
    borderRadius: radii.sm,
    marginBottom: spacing.xs,
  },
});
