import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { fonts, spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { resolveDashboardAction } from './dashboardApi';
import type { DashboardAction, DashboardNavigateTarget } from './dashboardTypes';
import { AlertsCard } from './sections/AlertsCard';
import { ChannelBreakdownCard } from './sections/ChannelBreakdownCard';
import { ContentReadinessCard } from './sections/ContentReadinessCard';
import { DashboardHeaderBar } from './sections/DashboardHeaderBar';
import { PlanCreditsCard } from './sections/PlanCreditsCard';
import { TeamCapacityCard } from './sections/TeamCapacityCard';
import { UsageDistributionCard } from './sections/UsageDistributionCard';
import { UsageSummaryCard } from './sections/UsageSummaryCard';
import { WorkspaceStatusCard } from './sections/WorkspaceStatusCard';
import { useTenantDashboard } from './useTenantDashboard';

type Props = {
  onNavigate: (target: DashboardNavigateTarget) => void;
};

export function DashboardScreen({ onNavigate }: Props) {
  const { colors } = useTheme();
  const { period, setPeriod, state, refreshing, refresh, reload } = useTenantDashboard('billing');

  function handleAction(action: DashboardAction) {
    const target = resolveDashboardAction(action.code);
    if (target) onNavigate(target);
  }

  return (
    <ScreenChrome title="Dashboard" subtitle="Your AI workspace at a glance">
      {state.kind === 'loading' ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.accent} accessibilityLabel="Loading dashboard" />
        </View>
      ) : null}

      {state.kind === 'forbidden' ? (
        <EmptyState title="Permission denied" body={state.message} />
      ) : null}

      {state.kind === 'error' ? (
        <View style={styles.center}>
          <EmptyState
            title={state.code === 'offline' ? 'Offline' : 'Dashboard unavailable'}
            body={state.message}
          />
          <Pressable onPress={reload} accessibilityRole="button" style={{ marginTop: spacing.md }}>
            <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>Try again</Text>
          </Pressable>
        </View>
      ) : null}

      {state.kind === 'ready' ? (
        <ScrollView
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
        >
          {state.stale || state.refreshError ? (
            <View
              style={[styles.banner, { backgroundColor: colors.banner, borderColor: colors.bannerBorder }]}
            >
              <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
                {state.refreshError
                  ? `Could not refresh (${state.refreshError}). Showing last successful snapshot.`
                  : 'Showing stale snapshot.'}
              </Text>
            </View>
          ) : null}
          {(state.data.partial_failures?.length ?? 0) > 0 ? (
            <View
              style={[styles.banner, { backgroundColor: colors.banner, borderColor: colors.bannerBorder }]}
            >
              <Text style={{ color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 }}>
                Some sections failed to load: {state.data.partial_failures?.join(', ')}
              </Text>
            </View>
          ) : null}

          <DashboardHeaderBar
            workspaceName={state.data.workspace.workspace_name}
            lastUpdated={state.data.generated_at}
            period={period}
            onPeriodChange={setPeriod}
            onRefresh={refresh}
            refreshing={refreshing}
            stale={state.stale}
          />

          <WorkspaceStatusCard
            title={state.data.workspace_status.title}
            explanation={state.data.workspace_status.explanation}
            state={state.data.workspace_status.state}
            action={state.data.workspace_status.primary_action}
            onAction={handleAction}
          />

          <PlanCreditsCard
            plan={state.data.plan_and_credits}
            onManageSubscription={() => onNavigate('subscription')}
            onBuyCredits={() => onNavigate('buy_credits')}
            onUpgrade={() => onNavigate('subscription')}
          />

          <UsageSummaryCard usage={state.data.usage_summary} periodLabel={state.data.period.label} />

          <ChannelBreakdownCard channels={state.data.channels} onAction={handleAction} />

          <UsageDistributionCard distribution={state.data.usage_distribution} />

          <ContentReadinessCard
            content={state.data.content_readiness}
            onOpenCm={() => onNavigate('cm')}
            onReviewFaq={() => onNavigate('faq')}
          />

          <TeamCapacityCard team={state.data.team_capacity} onManageUsers={() => onNavigate('users')} />

          <AlertsCard alerts={state.data.alerts} onAction={handleAction} />
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
