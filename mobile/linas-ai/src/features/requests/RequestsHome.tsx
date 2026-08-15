import { useState } from 'react';
import {
  FlatList,
  RefreshControl,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { EmptyState } from '../../components/EmptyState';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { RequestCardRow } from './RequestCardRow';
import { RequestFilterSheet } from './RequestFilterSheet';
import { RequestSearchBar } from './RequestSearchBar';
import { RequestSummaryCards } from './RequestSummaryCards';
import {
  assignRequest,
  changeRequestStatus,
  getRequest,
} from './requestsApi';
import {
  canManageRequests,
  canViewSensitiveRequests,
} from './requestsPermissions';
import { formatPrintSlip, nextStatusForBucket, statusBucket } from './requestsFormat';
import type { RequestCard, StatusBucket } from './requestsTypes';
import type { RequestsListState } from './useRequestsList';

type LiveChatTarget = { userId: string; conversationId: string };

type Props = {
  list: RequestsListState;
  onOpen: (item: RequestCard) => void;
  onOpenAiSetup: () => void;
  onOpenLiveChat: (target: LiveChatTarget) => void;
};

function filtersActive(list: RequestsListState): boolean {
  const f = list.filters;
  return f.platforms.length > 0 || Boolean(f.dateFrom || f.dateTo || f.assignedUserId);
}

function filterSummary(list: RequestsListState): string {
  const f = list.filters;
  const platforms = f.platforms.length ? f.platforms.length === 1 ? '1 platform' : `${f.platforms.length} platforms` : 'All platforms';
  const date =
    f.dateFrom || f.dateTo ? [f.dateFrom, f.dateTo].filter(Boolean).join(' – ') : 'Any date';
  const user = f.assignedUserId
    ? list.staff.find((s) => s.id === f.assignedUserId)?.label || 'Assigned'
    : 'All users';
  return `${platforms} · ${date} · ${user}`;
}

export function RequestsHome({ list, onOpen, onOpenAiSetup, onOpenLiveChat }: Props) {
  const { colors } = useTheme();
  const { tr, language } = useI18n();
  const [filterOpen, setFilterOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function withItem(item: RequestCard, fn: () => Promise<void>) {
    setBusyId(item.request_id);
    setActionError(null);
    try {
      await fn();
    } catch {
      setActionError(tr('reqActionError'));
    } finally {
      setBusyId(null);
    }
  }

  function assigneeLabel(item: RequestCard): string {
    if (!item.assigned_user_id) return 'Assign';
    return list.staff.find((s) => s.id === item.assigned_user_id)?.label || 'Assign';
  }

  async function onStatus(item: RequestCard, bucket: StatusBucket) {
    const next = nextStatusForBucket(item, bucket);
    if (!next) {
      if (statusBucket(item.status) !== bucket) setActionError(tr('reqStatusInvalid'));
      return;
    }
    if (!canManageRequests(list.user)) return;
    await withItem(item, async () => {
      const updated = await changeRequestStatus(item.request_id, {
        to_status: next,
        row_version: item.row_version,
      });
      list.patchItem({ ...item, ...updated });
    });
  }

  async function onAssign(item: RequestCard, userId: string | null) {
    if (!canManageRequests(list.user)) return;
    await withItem(item, async () => {
      const updated = await assignRequest(item.request_id, {
        assigned_user_id: userId,
        row_version: item.row_version,
      });
      list.patchItem({ ...item, ...updated });
    });
  }

  async function onChat(item: RequestCard) {
    let userId = item.external_customer_id;
    let conversationId = item.conversation_id;
    if (!userId || !conversationId) {
      try {
        const detail = await getRequest(item.request_id);
        userId = detail.external_customer_id;
        conversationId = detail.conversation_id;
      } catch {
        setActionError(tr('reqChatUnavailable'));
        return;
      }
    }
    if (userId && conversationId) {
      onOpenLiveChat({ userId, conversationId });
      return;
    }
    setActionError(tr('reqChatUnavailable'));
  }

  async function onPrint(item: RequestCard) {
    await withItem(item, async () => {
      const detail = await getRequest(item.request_id);
      const phone = canViewSensitiveRequests(list.user) ? detail.phone_normalized : item.phone_normalized;
      const message = formatPrintSlip(detail, phone);
      await Share.share({ message, title: `Request #${detail.request_number}` });
    });
  }

  if (list.loading && !list.refreshing) {
    return (
      <View style={styles.center}>
        <LinasLoadingIndicator variant="screen" />
      </View>
    );
  }
  if (list.errorKind === 'forbidden') {
    return <EmptyState title={tr('reqPermissionTitle')} body={tr('reqPermissionBody')} />;
  }
  if (list.errorKind === 'auth') {
    return <EmptyState title={tr('reqPermissionTitle')} body={tr('reqAuthBody')} />;
  }
  if (list.errorKind === 'offline') {
    return (
      <View style={styles.centerPad}>
        <EmptyState title={tr('reqOffline')} />
        <PrimaryButton label={tr('reqRetry')} onPress={() => void list.refresh()} />
      </View>
    );
  }
  if (list.errorKind === 'setup') {
    return (
      <View style={styles.centerPad}>
        <EmptyState title={tr('reqSetupRequiredTitle')} body={tr('reqSetupRequiredBody')} />
        <PrimaryButton label={tr('reqOpenAiSetup')} onPress={onOpenAiSetup} />
        <PrimaryButton label={tr('reqRetry')} onPress={() => void list.refresh()} variant="ghost" />
      </View>
    );
  }
  if (list.errorKind === 'other' || list.error) {
    return (
      <View style={styles.centerPad}>
        <EmptyState title={tr('reqLoadError')} />
        <PrimaryButton label={tr('reqRetry')} onPress={() => void list.refresh()} />
      </View>
    );
  }

  return (
    <View style={styles.flex}>
      <RequestSummaryCards
        counts={list.counts}
        selected={list.statusBucket}
        onSelect={list.setStatusBucket}
      />
      <RequestSearchBar
        value={list.search}
        onChange={list.setSearch}
        filterActive={filtersActive(list)}
        onOpenFilter={() => setFilterOpen(true)}
      />
      <Text style={[styles.summaryLine, { color: colors.textDim }]}>{filterSummary(list)}</Text>
      {actionError ? <Text style={[styles.err, { color: colors.danger }]}>{actionError}</Text> : null}

      <FlatList
        data={list.items}
        keyExtractor={(item) => item.request_id}
        renderItem={({ item }) => (
          <RequestCardRow
            item={item}
            assigneeLabel={assigneeLabel(item)}
            staff={list.staff}
            busy={busyId === item.request_id}
            language={language}
            onOpen={() => onOpen(item)}
            onStatus={(bucket) => void onStatus(item, bucket)}
            onAssign={(userId) => void onAssign(item, userId)}
            onChat={() => void onChat(item)}
            onPrint={() => void onPrint(item)}
          />
        )}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={list.refreshing} onRefresh={() => void list.refresh()} tintColor={colors.accent} />
        }
        onEndReached={() => void list.loadMore()}
        onEndReachedThreshold={0.4}
        ListEmptyComponent={<EmptyState title={tr('reqEmptyTitle')} body={tr('reqEmptyBody')} />}
        ListFooterComponent={
          list.loadingMore ? <LinasLoadingIndicator variant="inline" /> : null
        }
      />

      <RequestFilterSheet
        visible={filterOpen}
        applied={list.filters}
        staff={list.staff}
        search={list.search}
        onClose={() => setFilterOpen(false)}
        onApply={list.applyFilters}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  centerPad: { flex: 1, justifyContent: 'center', padding: spacing.xl, gap: spacing.md },
  summaryLine: { fontFamily: fonts.body, fontSize: 13, marginBottom: spacing.sm },
  list: { paddingBottom: spacing.xl, flexGrow: 1 },
  err: { fontFamily: fonts.body, fontSize: 13, marginBottom: 6 },
});
