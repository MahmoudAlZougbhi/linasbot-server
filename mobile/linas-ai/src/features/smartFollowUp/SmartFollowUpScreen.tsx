import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';

import { ApiError } from '../../api/client';
import { isNetworkFailure } from '../../api/networkError';
import { EmptyState } from '../../components/EmptyState';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { useModuleNav } from '../nav/ModuleNavContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { SmartFollowUpStepEditor } from './SmartFollowUpStepEditor';
import {
  DEFAULT_STEP_DELAYS,
  fetchSmartFollowUpSettings,
  isAiDisabledBlocker,
  isMetaSetupBlocker,
  previewSmartFollowUp,
  saveSmartFollowUpSettings,
  type FollowUpGoal,
  type SmartFollowUpSettings,
  type SmartFollowUpStep,
} from './smartFollowUpApi';

type LoadState =
  | { kind: 'loading' }
  | { kind: 'offline' }
  | { kind: 'forbidden' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: SmartFollowUpSettings };

function defaultSteps(): SmartFollowUpStep[] {
  return [
    { step_index: 1, enabled: true, delay_minutes: DEFAULT_STEP_DELAYS[0], goal: 'gentle_check_in' },
    { step_index: 2, enabled: true, delay_minutes: DEFAULT_STEP_DELAYS[1], goal: 'offer_more_help' },
    { step_index: 3, enabled: true, delay_minutes: DEFAULT_STEP_DELAYS[2], goal: 'politely_close' },
  ];
}

function validateLocal(steps: SmartFollowUpStep[]): StringKey | null {
  const enabled = steps.filter((s) => s.enabled).sort((a, b) => a.step_index - b.step_index);
  if (enabled.length === 0) return 'sfuValidationNoSteps';
  let prev = 0;
  for (const step of enabled) {
    if (step.delay_minutes <= prev) return 'sfuValidationDelays';
    if (step.delay_minutes > 23 * 60) return 'sfuValidationMaxDelay';
    prev = step.delay_minutes;
  }
  return null;
}

export function SmartFollowUpScreen() {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const nav = useModuleNav();
  const [load, setLoad] = useState<LoadState>({ kind: 'loading' });
  const [enabled, setEnabled] = useState(false);
  const [businessHoursOnly, setBusinessHoursOnly] = useState(true);
  const [steps, setSteps] = useState<SmartFollowUpStep[]>(defaultSteps);
  const [settingsVersion, setSettingsVersion] = useState(0);
  const [blockers, setBlockers] = useState<SmartFollowUpSettings['blockers']>();
  const [stopRules, setStopRules] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationKey, setValidationKey] = useState<StringKey | null>(null);

  const applySettings = useCallback((data: SmartFollowUpSettings) => {
    setEnabled(data.enabled);
    setBusinessHoursOnly(data.business_hours_only);
    setSteps(data.steps.length ? [...data.steps].sort((a, b) => a.step_index - b.step_index) : defaultSteps());
    setSettingsVersion(data.settings_version);
    setBlockers(data.blockers);
    setStopRules(data.stop_rules ?? []);
  }, []);

  const reload = useCallback(async () => {
    setLoad({ kind: 'loading' });
    setError(null);
    setNotice(null);
    try {
      const data = await fetchSmartFollowUpSettings();
      applySettings(data);
      setLoad({ kind: 'ready', data });
    } catch (err) {
      if (isNetworkFailure(err)) {
        setLoad({ kind: 'offline' });
        return;
      }
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        setLoad({ kind: 'forbidden' });
        return;
      }
      setLoad({
        kind: 'error',
        message: err instanceof Error ? err.message : tr('sfuLoadError'),
      });
    }
  }, [applySettings, tr]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (nav.activeArea === 'smartFollowUp') {
      void reload();
    }
  }, [nav.areaFocusNonce, nav.activeArea, reload]);

  const waConnected = blockers?.whatsapp_connected === true;
  const aiBlocker = blockers?.ai_blocker ?? null;

  const blockerBanner = useMemo(() => {
    if (load.kind !== 'ready') return null;
    if (blockers?.whatsapp_connected === false) {
      return { key: 'wa' as const, text: tr('sfuWhatsAppDisconnected'), cta: tr('sfuOpenIntegrations') };
    }
    if (isAiDisabledBlocker(aiBlocker)) {
      return { key: 'ai' as const, text: tr('sfuAiDisabled'), cta: null };
    }
    if (isMetaSetupBlocker(aiBlocker)) {
      return { key: 'meta' as const, text: tr('sfuMetaSetupRequired'), cta: tr('sfuOpenIntegrations') };
    }
    if (aiBlocker === 'published_cm_missing' || aiBlocker === 'published_cm_unavailable') {
      return { key: 'cm' as const, text: tr('sfuMetaSetupRequired'), cta: null };
    }
    return null;
  }, [aiBlocker, blockers?.whatsapp_connected, load.kind, tr]);

  async function onSave() {
    const v = validateLocal(steps);
    if (v) {
      setValidationKey(v);
      setError(tr(v));
      return;
    }
    setValidationKey(null);
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const data = await saveSmartFollowUpSettings({
        enabled,
        business_hours_only: businessHoursOnly,
        settings_version: settingsVersion,
        steps,
      });
      applySettings(data);
      setLoad({ kind: 'ready', data });
      setNotice(tr('sfuSaveSuccess'));
    } catch (err) {
      if (isNetworkFailure(err)) {
        setError(tr('sfuOffline'));
      } else if (err instanceof ApiError && err.status === 403) {
        setError(tr('sfuPermissionDenied'));
      } else if (err instanceof ApiError && err.status === 409) {
        setError(tr('sfuVersionConflict'));
        void reload();
      } else if (err instanceof ApiError && err.status === 400) {
        setError(tr('sfuSaveValidationError'));
      } else {
        setError(tr('sfuSaveError'));
      }
    } finally {
      setSaving(false);
    }
  }

  async function onPreview() {
    const goal = (steps.find((s) => s.enabled)?.goal ?? 'gentle_check_in') as FollowUpGoal;
    Alert.alert(tr('sfuPreviewTitle'), tr('sfuPreviewDisclose'), [
      { text: tr('usersCancel'), style: 'cancel' },
      {
        text: tr('sfuPreviewRun'),
        onPress: () => {
          void (async () => {
            setPreviewing(true);
            setError(null);
            setNotice(null);
            try {
              const result = await previewSmartFollowUp(goal);
              if (!result.success) {
                if (result.error === 'whatsapp_disconnected') {
                  setError(tr('sfuWhatsAppDisconnected'));
                } else if (result.error === 'insufficient_credits') {
                  setError(tr('sfuPreviewCredits'));
                } else {
                  setError(result.message || tr('sfuPreviewError'));
                }
                return;
              }
              setNotice(result.preview_text || tr('sfuPreviewEmpty'));
            } catch (err) {
              if (isNetworkFailure(err)) setError(tr('sfuOffline'));
              else if (err instanceof ApiError && err.status === 403) setError(tr('sfuPermissionDenied'));
              else if (err instanceof ApiError && err.status === 409) setError(tr('sfuWhatsAppDisconnected'));
              else if (err instanceof ApiError && err.status === 402) setError(tr('sfuPreviewCredits'));
              else setError(tr('sfuPreviewError'));
            } finally {
              setPreviewing(false);
            }
          })();
        },
      },
    ]);
  }

  const stopSummary = stopRules.length
    ? stopRules.map((r) => r.replace(/_/g, ' ')).join(' · ')
    : tr('sfuStopRulesDefault');

  return (
    <ScreenChrome title={tr('sfuTitle')} subtitle={tr('sfuSubtitle')}>
      {load.kind === 'loading' ? <ActivityIndicator color={colors.accent} /> : null}

      {load.kind === 'offline' ? (
        <EmptyState title={tr('sfuOffline')} body={tr('tapToRetry')} />
      ) : null}
      {load.kind === 'forbidden' ? (
        <EmptyState title={tr('sfuPermissionDenied')} body={tr('sfuPermissionDeniedBody')} />
      ) : null}
      {load.kind === 'error' ? (
        <EmptyState title={tr('sfuLoadError')} body={load.message} />
      ) : null}

      {(load.kind === 'offline' || load.kind === 'error') ? (
        <PrimaryButton label={tr('proposalRetry')} onPress={() => void reload()} variant="ghost" />
      ) : null}
      {load.kind === 'forbidden' ? (
        <PrimaryButton
          label={tr('loginOrRegister')}
          onPress={() => nav.requestLogin()}
          variant="ghost"
        />
      ) : null}

      {load.kind === 'ready' ? (
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {blockerBanner ? (
            <View style={[styles.banner, { backgroundColor: colors.banner, borderColor: colors.bannerBorder }]}>
              <Text style={{ color: colors.warning, fontFamily: fonts.bodyMedium }}>{blockerBanner.text}</Text>
              {blockerBanner.cta ? (
                <PrimaryButton
                  label={blockerBanner.cta}
                  onPress={() => nav.openArea('integrations')}
                  variant="ghost"
                  style={styles.bannerCta}
                />
              ) : null}
              {!waConnected ? (
                <Text style={[styles.bannerNote, { color: colors.textMuted }]}>
                  {tr('sfuConnectedOnlyFromStatus')}
                </Text>
              ) : null}
            </View>
          ) : null}

          <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <View style={styles.rowBetween}>
              <View style={styles.flex}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{tr('sfuMasterToggle')}</Text>
                <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
                  {tr('sfuMasterToggleHint')}
                </Text>
              </View>
              <Switch
                value={enabled}
                onValueChange={setEnabled}
                trackColor={{ false: colors.border, true: colors.accent }}
                thumbColor={colors.surface}
                accessibilityLabel={tr('sfuMasterToggle')}
              />
            </View>
          </View>

          {steps.map((step, index) => (
            <SmartFollowUpStepEditor
              key={step.step_index}
              step={step}
              defaultDelay={DEFAULT_STEP_DELAYS[Math.min(index, DEFAULT_STEP_DELAYS.length - 1)] ?? 30}
              onChange={(next) => {
                setSteps((prev) => prev.map((s) => (s.step_index === next.step_index ? next : s)));
                setValidationKey(null);
              }}
            />
          ))}

          <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <View style={styles.rowBetween}>
              <View style={styles.flex}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{tr('sfuBusinessHours')}</Text>
                <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
                  {tr('sfuBusinessHoursHint')}
                </Text>
              </View>
              <Switch
                value={businessHoursOnly}
                onValueChange={setBusinessHoursOnly}
                trackColor={{ false: colors.border, true: colors.accent }}
                thumbColor={colors.surface}
                accessibilityLabel={tr('sfuBusinessHours')}
              />
            </View>
          </View>

          <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <Text style={[styles.cardTitle, { color: colors.text }]}>{tr('sfuAiWrites')}</Text>
            <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 14, marginTop: 4 }}>
              {tr('sfuAiWritesBody')}
            </Text>
          </View>

          <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <Text style={[styles.cardTitle, { color: colors.text }]}>{tr('sfuStopRules')}</Text>
            <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13, marginTop: 6 }}>
              {stopSummary}
            </Text>
          </View>

          {validationKey ? (
            <Text style={{ color: colors.danger, fontFamily: fonts.body }}>{tr(validationKey)}</Text>
          ) : null}
          {error ? <Text style={{ color: colors.danger, fontFamily: fonts.body }}>{error}</Text> : null}
          {notice ? <Text style={{ color: colors.mint, fontFamily: fonts.body }}>{notice}</Text> : null}

          <PrimaryButton label={tr('sfuSave')} onPress={() => void onSave()} loading={saving} />
          <PrimaryButton
            label={tr('sfuPreview')}
            onPress={() => void onPreview()}
            loading={previewing}
            variant="ghost"
            disabled={!waConnected}
          />
        </ScrollView>
      ) : null}
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingBottom: 40, gap: spacing.md },
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
  },
  cardTitle: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  flex: { flex: 1 },
  banner: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  bannerCta: { alignSelf: 'flex-start' },
  bannerNote: { fontFamily: fonts.body, fontSize: 12 },
});
