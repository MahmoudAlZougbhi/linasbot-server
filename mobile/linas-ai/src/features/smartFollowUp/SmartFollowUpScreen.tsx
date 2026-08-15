import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
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
import { SmartFollowUpChannelsCard } from './SmartFollowUpChannelsCard';
import { SmartFollowUpStepsCard } from './SmartFollowUpStepsCard';
import { SFU_CARD_BORDER, SFU_TEAL } from './smartFollowUpDesign';
import {
  DEFAULT_CHANNELS_ENABLED,
  type FollowUpChannelKey,
  type FollowUpChannelsEnabled,
  normalizeChannelsEnabled,
  supportedChannelsSelected,
} from './smartFollowUpOptions';
import {
  DEFAULT_STEP_DELAYS,
  fetchSmartFollowUpSettings,
  saveSmartFollowUpSettings,
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

function featureEnabledFromSteps(steps: SmartFollowUpStep[]): boolean {
  return steps.some((s) => s.enabled);
}

function validateLocal(
  steps: SmartFollowUpStep[],
  channels: FollowUpChannelsEnabled,
): StringKey | null {
  if (!supportedChannelsSelected(channels)) return 'sfuValidationNoChannels';
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
  const [businessHoursOnly, setBusinessHoursOnly] = useState(true);
  const [channels, setChannels] = useState<FollowUpChannelsEnabled>(DEFAULT_CHANNELS_ENABLED);
  const [steps, setSteps] = useState<SmartFollowUpStep[]>(defaultSteps);
  const [settingsVersion, setSettingsVersion] = useState(0);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationKey, setValidationKey] = useState<StringKey | null>(null);

  const applySettings = useCallback((data: SmartFollowUpSettings) => {
    setBusinessHoursOnly(data.business_hours_only);
    setChannels(normalizeChannelsEnabled(data.channels_enabled));
    setSteps(data.steps.length ? [...data.steps].sort((a, b) => a.step_index - b.step_index) : defaultSteps());
    setSettingsVersion(data.settings_version);
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

  const formDisabled = useMemo(() => saving || load.kind !== 'ready', [load.kind, saving]);

  function toggleChannel(channel: FollowUpChannelKey) {
    setChannels((prev) => ({ ...prev, [channel]: !prev[channel] }));
    setValidationKey(null);
  }

  function selectAllChannels() {
    setChannels({
      instagram_dm: true,
      facebook_messenger: true,
      whatsapp_cloud: true,
    });
    setValidationKey(null);
  }

  async function onSave() {
    const v = validateLocal(steps, channels);
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
        enabled: featureEnabledFromSteps(steps),
        business_hours_only: businessHoursOnly,
        settings_version: settingsVersion,
        channels_enabled: channels,
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

  return (
    <ScreenChrome title={tr('sfuTitle')} subtitle={tr('sfuSubtitle')}>
      {load.kind === 'loading' ? <ActivityIndicator color={SFU_TEAL} /> : null}

      {load.kind === 'offline' ? (
        <EmptyState title={tr('sfuOffline')} body={tr('tapToRetry')} />
      ) : null}
      {load.kind === 'forbidden' ? (
        <EmptyState title={tr('sfuPermissionDenied')} body={tr('sfuPermissionDeniedBody')} />
      ) : null}
      {load.kind === 'error' ? <EmptyState title={tr('sfuLoadError')} body={load.message} /> : null}

      {(load.kind === 'offline' || load.kind === 'error') ? (
        <PrimaryButton label={tr('proposalRetry')} onPress={() => void reload()} variant="ghost" />
      ) : null}
      {load.kind === 'forbidden' ? (
        <PrimaryButton label={tr('loginOrRegister')} onPress={() => nav.requestLogin()} variant="ghost" />
      ) : null}

      {load.kind === 'ready' ? (
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <View style={[styles.card, { backgroundColor: colors.surface, borderColor: SFU_CARD_BORDER }]}>
            <View style={styles.rowBetween}>
              <View style={styles.flex}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{tr('sfuBusinessHours')}</Text>
                <Text style={[styles.cardHint, { color: colors.textMuted }]}>{tr('sfuBusinessHoursHint')}</Text>
              </View>
              <Switch
                value={businessHoursOnly}
                onValueChange={setBusinessHoursOnly}
                disabled={formDisabled}
                trackColor={{ false: colors.border, true: SFU_TEAL }}
                thumbColor={colors.surface}
                accessibilityLabel={tr('sfuBusinessHours')}
              />
            </View>
          </View>

          <SmartFollowUpChannelsCard
            channels={channels}
            disabled={formDisabled}
            onToggle={toggleChannel}
            onSelectAll={selectAllChannels}
          />

          <SmartFollowUpStepsCard
            steps={steps}
            disabled={formDisabled}
            onChange={(next) => {
              setSteps((prev) => prev.map((s) => (s.step_index === next.step_index ? next : s)));
              setValidationKey(null);
            }}
          />

          {validationKey ? (
            <Text style={{ color: colors.danger, fontFamily: fonts.body }}>{tr(validationKey)}</Text>
          ) : null}
          {error ? <Text style={{ color: colors.danger, fontFamily: fonts.body }}>{error}</Text> : null}
          {notice ? <Text style={{ color: colors.mint, fontFamily: fonts.body }}>{notice}</Text> : null}

          <PrimaryButton
            label={tr('sfuSaveChanges')}
            onPress={() => void onSave()}
            loading={saving}
            style={styles.saveBtn}
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
    padding: spacing.lg,
  },
  cardTitle: { fontFamily: fonts.display, fontSize: 16 },
  cardHint: { fontFamily: fonts.body, fontSize: 13, marginTop: 4 },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  flex: { flex: 1 },
  saveBtn: {
    marginTop: spacing.xs,
  },
});
