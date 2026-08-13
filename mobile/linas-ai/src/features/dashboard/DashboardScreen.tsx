import { useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import type { DashboardNavigateTarget } from './dashboardTypes';
import { ChannelActivityTable } from './sections/ChannelActivityTable';
import { DashboardHeader } from './sections/DashboardHeader';
import { DashboardRefreshButton } from './sections/DashboardRefreshButton';
import { GrowthPlanCard } from './sections/GrowthPlanCard';
import { OwnerCopilotCard } from './sections/OwnerCopilotCard';
import { TotalActivityGrid } from './sections/TotalActivityGrid';
import { useTenantDashboard } from './useTenantDashboard';

type Props = {
  onNavigate: (target: DashboardNavigateTarget) => void;
};

function periodRangeIso(data: { period: { start: string; end: string } }): { start: string; end: string } {
  const endDt = new Date(data.period.end);
  endDt.setUTCDate(endDt.getUTCDate() - 1);
  return {
    start: data.period.start.slice(0, 10),
    end: endDt.toISOString().slice(0, 10),
  };
}

export function DashboardScreen({ onNavigate }: Props) {
  const { colors } = useTheme();
  const { tr, language } = useI18n();
  const { period, setPeriod, state, refreshing, refresh } = useTenantDashboard();
  const [copilotExpanded, setCopilotExpanded] = useState(false);

  return (
    <ScreenChrome
      title={tr('dashTitle')}
      centerTitle
      headerRight={<DashboardRefreshButton onRefresh={refresh} refreshing={refreshing} />}
    >
      {state.kind === 'loading' ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} accessibilityLabel="Loading dashboard" />
        </View>
      ) : null}

      {state.kind === 'forbidden' ? (
        <EmptyState title={tr('dashPermissionDenied')} body={state.message} />
      ) : null}

      {state.kind === 'error' ? (
        <View style={styles.center}>
          <EmptyState
            title={state.code === 'offline' ? tr('dashOffline') : tr('dashUnavailable')}
            body={state.message}
          />
          <Pressable onPress={refresh} accessibilityRole="button" style={{ marginTop: spacing.md }}>
            <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>{tr('dashTryAgain')}</Text>
          </Pressable>
        </View>
      ) : null}

      {state.kind === 'ready' ? (
        <ScrollView
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
        >
          {state.stale || state.refreshError ? (
            <View style={[styles.banner, { backgroundColor: colors.banner, borderColor: colors.bannerBorder }]}>
              <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
                {state.refreshError ? tr('dashRefreshFailed') : tr('dashStaleBanner')}
              </Text>
            </View>
          ) : null}
          {(state.data.partial_failures?.length ?? 0) > 0 ? (
            <View style={[styles.banner, { backgroundColor: colors.banner, borderColor: colors.bannerBorder }]}>
              <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
                {tr('dashPartialFailure')} {state.data.partial_failures?.join(', ')}
              </Text>
            </View>
          ) : null}

          <DashboardHeader
            period={period}
            rangeStart={periodRangeIso(state.data).start}
            rangeEnd={periodRangeIso(state.data).end}
            onPeriodChange={setPeriod}
          />

          <GrowthPlanCard
            plan={state.data.plan_and_credits}
            locale={language === 'ar' ? 'ar' : language === 'fr' ? 'fr' : 'en'}
            onBuyCredits={() => onNavigate('buy_credits')}
            onUpgrade={() => onNavigate('subscription')}
          />

          <TotalActivityGrid
            activity={state.data.activity_summary?.total_activity}
            unavailable={state.data.activity_summary?.availability !== 'ok'}
          />

          <ChannelActivityTable
            channels={state.data.activity_summary?.channels}
            unavailable={state.data.activity_summary?.availability !== 'ok'}
          />

          <OwnerCopilotCard
            copilot={state.data.activity_summary?.owner_copilot}
            expanded={copilotExpanded}
            onToggle={() => setCopilotExpanded((v) => !v)}
            onOpenChat={() => onNavigate('chat')}
          />
        </ScrollView>
      ) : null}
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 48, gap: spacing.md },
  center: { paddingVertical: spacing.xl, alignItems: 'center' },
  banner: {
    borderWidth: 1,
    borderRadius: 12,
    padding: spacing.md,
  },
});
