import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { WebChatCustomModePanel } from './WebChatCustomModePanel';
import { WebChatLivePreview } from './WebChatLivePreview';
import { WebChatWidgetCustomize } from './WebChatWidgetCustomize';
import {
  checkWebChatInstallation,
  fetchWebChatSettings,
  rotateWebChatKey,
  saveWebChatSettings,
  type WebChatSettings,
} from './webChatApi';
import {
  fetchWebChannelEntitledFromEntitlements,
  resolveWebPlanAllowed,
} from './webChatPlanAccess';
import type { WebChatAppearance, WebChatInstallationStatus } from './webChatTypes';

type Props = {
  onBack: () => void;
  onError?: (message: string) => void;
  onNotice?: (message: string) => void;
};

function statusLabel(status: WebChatInstallationStatus, tr: (k: string) => string) {
  if (status === 'connected') return tr('webChatStatusConnected');
  if (status === 'domain_mismatch') return tr('webChatStatusDomainMismatch');
  if (status === 'disabled') return tr('webChatStatusDisabled');
  return tr('webChatStatusWaiting');
}

export function WebsiteIntegrationScreen({ onBack, onError, onNotice }: Props) {
  const { tr } = useI18n();
  const [settings, setSettings] = useState<WebChatSettings | null>(null);
  const [entitlementWeb, setEntitlementWeb] = useState<boolean | null>(null);
  const [siteUrl, setSiteUrl] = useState('');
  const [appearance, setAppearance] = useState<WebChatAppearance | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const webPlanAllowed = resolveWebPlanAllowed(settings, entitlementWeb);
  const planBlocked = !loading && !webPlanAllowed;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [data, entitled] = await Promise.all([
        fetchWebChatSettings(),
        fetchWebChannelEntitledFromEntitlements(),
      ]);
      setSettings(data);
      setEntitlementWeb(entitled);
      setSiteUrl(data.site_url || '');
      setAppearance(data.appearance);
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

  async function persist(patch: Parameters<typeof saveWebChatSettings>[0]) {
    if (planBlocked) {
      onError?.(settings?.membership_message || tr('webChatPlanRequired'));
      return;
    }
    setBusy(true);
    try {
      const data = await saveWebChatSettings(patch);
      setSettings(data);
      setSiteUrl(data.site_url || '');
      setAppearance(data.appearance);
      onNotice?.(tr('webChatSaved'));
    } catch (err) {
      onError?.(tr('integrationsActionError'));
    } finally {
      setBusy(false);
    }
  }

  async function onToggleEnabled(value: boolean) {
    await persist({ site_url: siteUrl.trim(), enabled: value, appearance: appearance ?? undefined });
  }

  async function onSaveAll() {
    await persist({
      site_url: siteUrl.trim(),
      enabled: settings?.enabled,
      integration_mode: settings?.integration_mode,
      appearance: appearance ?? undefined,
    });
  }

  async function onModeChange(mode: 'linas_widget' | 'custom_chat') {
    await persist({
      site_url: siteUrl.trim(),
      enabled: settings?.enabled,
      integration_mode: mode,
      appearance: appearance ?? undefined,
    });
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

  async function onCheckInstall() {
    setBusy(true);
    try {
      const res = await checkWebChatInstallation();
      setSettings((prev) =>
        prev
          ? {
              ...prev,
              installation_status: res.installation_status,
              installation: res.installation,
            }
          : prev,
      );
      onNotice?.(statusLabel(res.installation_status, tr));
    } catch {
      onError?.(tr('integrationsActionError'));
    } finally {
      setBusy(false);
    }
  }

  async function onTestConnection() {
    setBusy(true);
    try {
      const res = await checkWebChatInstallation();
      if (res.installation_status === 'connected') onNotice?.(tr('webChatTestOk'));
      else onError?.(tr('webChatTestFailed'));
    } catch {
      onError?.(tr('webChatTestFailed'));
    } finally {
      setBusy(false);
    }
  }

  const installHint = useMemo(() => {
    const seen = settings?.installation.last_seen_at;
    if (!seen) return tr('webChatInstallNever');
    return `${tr('webChatInstallSeen')}: ${new Date(seen * 1000).toLocaleString()}`;
  }, [settings?.installation.last_seen_at, tr]);

  return (
    <ScreenChrome title={tr('platformWeb')} subtitle={tr('webChatSubtitle')} onBack={onBack}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        {planBlocked ? <Text style={styles.warn}>{tr('webChatPlanRequired')}</Text> : null}

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
          editable={!busy && !planBlocked}
        />

        <View style={styles.rowBetween}>
          <Text style={styles.label}>{tr('webChatEnableToggle')}</Text>
          <Switch
            value={Boolean(settings?.enabled)}
            onValueChange={(v) => void onToggleEnabled(v)}
            disabled={busy || planBlocked || loading}
          />
        </View>

        <View style={styles.statusPill}>
          <Text style={styles.statusText}>
            {statusLabel(settings?.installation_status || 'waiting', tr)}
          </Text>
        </View>

        <Text style={styles.section}>{tr('webChatModeTitle')}</Text>
        <View style={styles.modeRow}>
          {(['linas_widget', 'custom_chat'] as const).map((mode) => {
            const active = settings?.integration_mode === mode;
            return (
              <Pressable
                key={mode}
                disabled={busy || planBlocked}
                onPress={() => void onModeChange(mode)}
                style={[styles.modeCard, active && styles.modeCardOn]}
              >
                <Text style={styles.modeTitle}>
                  {tr(mode === 'linas_widget' ? 'webChatModeWidget' : 'webChatModeCustom')}
                </Text>
                <Text style={styles.modeSub}>
                  {tr(mode === 'linas_widget' ? 'webChatModeWidgetSub' : 'webChatModeCustomSub')}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {settings?.integration_mode === 'linas_widget' && appearance ? (
          <>
            <WebChatWidgetCustomize
              appearance={appearance}
              contrastWarnings={settings.contrast_warnings || []}
              disabled={busy || planBlocked}
              onChange={setAppearance}
            />
            <WebChatLivePreview appearance={appearance} />
            <Text style={styles.label}>{tr('webChatEmbedTitle')}</Text>
            <Text selectable style={styles.code}>
              {settings.embed_snippet}
            </Text>
            <Pressable disabled={busy} onPress={() => void copyEmbed()} style={styles.linkBtn}>
              <Text style={styles.linkText}>{tr('webChatCopyEmbed')}</Text>
            </Pressable>
            <Text style={styles.hint}>{installHint}</Text>
            <Pressable disabled={busy} onPress={() => void onCheckInstall()} style={styles.btn}>
              <Text style={styles.btnText}>{tr('webChatCheckInstall')}</Text>
            </Pressable>
            <Pressable disabled={busy} onPress={onRotateKey} style={styles.linkBtn}>
              <Text style={styles.linkText}>{tr('webChatRotateKeyMenu')}</Text>
            </Pressable>
          </>
        ) : null}

        {settings?.integration_mode === 'custom_chat' ? (
          <WebChatCustomModePanel
            settings={settings}
            busy={busy}
            onRotateKey={onRotateKey}
            onTestConnection={() => void onTestConnection()}
            onNotice={(msg) => onNotice?.(msg)}
          />
        ) : null}

        {!planBlocked ? (
          <Pressable disabled={busy || loading} onPress={() => void onSaveAll()} style={styles.btnPrimary}>
            <Text style={styles.btnText}>{tr('webChatSave')}</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: spacing.xl },
  warn: { fontFamily: fonts.body, fontSize: 13, color: colors.warning },
  label: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.text },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 10,
    fontFamily: fonts.body,
    fontSize: 14,
    color: colors.text,
  },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  statusPill: {
    alignSelf: 'flex-start',
    backgroundColor: colors.accentSoft,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  statusText: { fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.accent },
  section: { fontFamily: fonts.bodyMedium, fontSize: 15, color: colors.text, marginTop: spacing.sm },
  modeRow: { gap: spacing.sm },
  modeCard: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    backgroundColor: colors.surface,
  },
  modeCardOn: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  modeTitle: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.text },
  modeSub: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted, marginTop: 4 },
  code: {
    fontFamily: fonts.body,
    fontSize: 12,
    color: colors.textMuted,
    backgroundColor: colors.input,
    padding: spacing.sm,
    borderRadius: radii.sm,
  },
  hint: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted },
  btn: {
    alignSelf: 'flex-start',
    backgroundColor: colors.input,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
  },
  btnPrimary: {
    alignSelf: 'stretch',
    backgroundColor: colors.accent,
    borderRadius: radii.sm,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: spacing.md,
  },
  btnText: { fontFamily: fonts.bodyMedium, color: '#fff', fontSize: 14 },
  linkBtn: { paddingVertical: 6 },
  linkText: { fontFamily: fonts.bodyMedium, color: colors.accent, fontSize: 14 },
});
