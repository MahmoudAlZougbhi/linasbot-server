import { useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { BuyCreditsSheet } from '../billing/BuyCreditsSheet';
import { useBuyCreditsFlow } from '../billing/useBuyCreditsFlow';
import { ScreenChrome } from '../shared/ScreenChrome';
import { DASH_CANVAS } from './dashboardChrome';
import { dashboardQueryRange } from './dashboardFormat';
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
  active?: boolean;
};

export function DashboardScreen({ onNavigate, active = true }: Props) {
  const { colors } = useTheme();
  const { tr, language } = useI18n();
  const { period, setPeriod, resetToDefaultPeriod, state, refreshing, refresh } = useTenantDashboard();
  const queryRange = dashboardQueryRange(period);
  const [copilotExpanded, setCopilotExpanded] = useState(false);
  const credits = useBuyCreditsFlow(refresh);

  useEffect(() => {
    if (active) resetToDefaultPeriod();
  }, [active, resetToDefaultPeriod]);

  return (
    <ScreenChrome
      title={tr('dashTitle')}
      canvasColor={DASH_CANVAS}
      headerRight={<DashboardRefreshButton onRefresh={refresh} refreshing={refreshing} />}
    >
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

      {state.kind === 'loading' || state.kind === 'ready' ? (
        <ScrollView
          contentContainerStyle={styles.list}
          refreshControl={
            state.kind === 'ready' ? (
              <RefreshControl refreshing={refreshing} onRefresh={refresh} />
            ) : undefined
          }
        >
          <DashboardHeader
            period={period}
            rangeStart={queryRange.start}
            rangeEnd={queryRange.end}
            onPeriodChange={setPeriod}
          />

          {state.kind === 'loading' ? <LinasLoadingIndicator variant="screen" /> : null}

          {state.kind === 'ready' && (state.stale || state.refreshError) ? (
            <View style={[styles.banner, { backgroundColor: colors.banner, borderColor: colors.bannerBorder }]}>
              <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
                {state.refreshError ? tr('dashRefreshFailed') : tr('dashStaleBanner')}
              </Text>
            </View>
          ) : null}
          {state.kind === 'ready' && (state.data.partial_failures?.length ?? 0) > 0 ? (
            <View style={[styles.banner, { backgroundColor: colors.banner, borderColor: colors.bannerBorder }]}>
              <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
                {tr('dashPartialFailure')} {state.data.partial_failures?.join(', ')}
              </Text>
            </View>
          ) : null}

          {state.kind === 'ready' ? (
            <>
              <GrowthPlanCard
                plan={state.data.plan_and_credits}
                locale={language === 'ar' ? 'ar' : language === 'fr' ? 'fr' : 'en'}
                onBuyCredits={() => credits.setOpen(true)}
                onUpgrade={() => onNavigate('choose_plan')}
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
            </>
          ) : null}
        </ScrollView>
      ) : null}

      <BuyCreditsSheet
        visible={credits.open}
        prices={credits.prices}
        purchasing={credits.purchasing}
        locale={credits.locale}
        tr={credits.tr}
        onClose={() => credits.setOpen(false)}
        onBuy={(pack) => void credits.buy(pack)}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 48, gap: 14 },
  center: { paddingVertical: spacing.xl, alignItems: 'center' },
  banner: {
    borderWidth: 1,
    borderRadius: 12,
    padding: spacing.md,
  },
});
