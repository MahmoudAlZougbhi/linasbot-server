import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { EmptyState } from '../../components/EmptyState';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { HIT, fonts, radii, spacing, useTheme } from '../../theme';
import { RequestCardRow } from './RequestCardRow';
import type { RequestsListState } from './useRequestsList';
import {
  COUNTER_STATUSES,
  REQUEST_STATUSES,
  SOURCE_CHANNELS,
  STATUS_LABEL_KEYS,
  CHANNEL_LABEL_KEYS,
  type DatePreset,
  type RequestCard,
  type TypeFilter,
} from './requestsTypes';

type Props = {
  list: RequestsListState;
  onOpen: (item: RequestCard) => void;
  onOpenAiSetup: () => void;
};

type Chip = { id: string; labelKey: StringKey };

const TYPE_CHIPS: { id: TypeFilter; labelKey: StringKey }[] = [
  { id: 'all', labelKey: 'reqFilterAll' },
  { id: 'ORDER', labelKey: 'reqFilterOrders' },
  { id: 'APPOINTMENT', labelKey: 'reqFilterAppointments' },
  { id: 'OTHER', labelKey: 'reqFilterOther' },
];

const DATE_CHIPS: { id: DatePreset; labelKey: StringKey }[] = [
  { id: 'all', labelKey: 'reqDateAll' },
  { id: 'today', labelKey: 'reqDateToday' },
  { id: 'last7', labelKey: 'reqDateLast7' },
  { id: 'last30', labelKey: 'reqDateLast30' },
];

function ChipRow({
  chips,
  selected,
  onSelect,
}: {
  chips: Chip[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
      {chips.map((chip) => {
        const active = selected === chip.id;
        return (
          <Pressable
            key={chip.id}
            onPress={() => onSelect(active && chip.id !== 'all' ? null : chip.id)}
            style={[
              styles.chip,
              {
                backgroundColor: active ? colors.accentSoft : colors.surfaceAlt,
                borderColor: active ? colors.accent : colors.border,
              },
            ]}
          >
            <Text style={{ color: active ? colors.accent : colors.textMuted, fontFamily: fonts.bodyMedium, fontSize: 12 }}>
              {tr(chip.labelKey)}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

export function RequestsHome({ list, onOpen, onOpenAiSetup }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  if (list.loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} />
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

  const statusChips: Chip[] = [
    { id: '', labelKey: 'reqStatusAny' },
    ...REQUEST_STATUSES.map((s) => ({ id: s, labelKey: STATUS_LABEL_KEYS[s] })),
  ];
  const channelChips: Chip[] = [
    { id: '', labelKey: 'reqChannelAny' },
    ...SOURCE_CHANNELS.map((c) => ({ id: c, labelKey: CHANNEL_LABEL_KEYS[c] })),
  ];

  return (
    <View style={styles.flex}>
      {list.setupRequired ? (
        <View style={[styles.setup, { backgroundColor: colors.accentSoft, borderColor: colors.accent }]}>
          <Text style={[styles.setupTitle, { color: colors.text }]}>{tr('reqSetupRequiredTitle')}</Text>
          <Text style={[styles.setupBody, { color: colors.textMuted }]}>{tr('reqSetupRequiredBody')}</Text>
          <PrimaryButton label={tr('reqOpenAiSetup')} onPress={onOpenAiSetup} style={styles.setupBtn} />
        </View>
      ) : null}

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.counters}>
        {COUNTER_STATUSES.map((status) => (
          <Pressable
            key={status}
            onPress={() => list.setStatusFilter(list.statusFilter === status ? null : status)}
            style={[
              styles.counter,
              {
                backgroundColor: list.statusFilter === status ? colors.accentSoft : colors.surface,
                borderColor: colors.border,
              },
            ]}
          >
            <Text style={[styles.counterN, { color: colors.text }]}>{list.counts[status] ?? 0}</Text>
            <Text style={[styles.counterL, { color: colors.textMuted }]}>
              {tr(STATUS_LABEL_KEYS[status])}
            </Text>
          </Pressable>
        ))}
      </ScrollView>

      <View style={[styles.searchWrap, { backgroundColor: colors.input, borderColor: colors.border }]}>
        <AppIcon icon={feather('search')} size={16} color={colors.textDim} />
        <TextInput
          value={list.search}
          onChangeText={list.setSearch}
          placeholder={tr('reqSearchPlaceholder')}
          placeholderTextColor={colors.textDim}
          style={[styles.search, { color: colors.text }]}
          accessibilityLabel={tr('reqSearchPlaceholder')}
          autoCorrect={false}
          autoCapitalize="none"
        />
      </View>

      <ChipRow
        chips={TYPE_CHIPS}
        selected={list.typeFilter}
        onSelect={(id) => list.setTypeFilter((id as TypeFilter) || 'all')}
      />
      <ChipRow
        chips={statusChips}
        selected={list.statusFilter ?? ''}
        onSelect={(id) => list.setStatusFilter(id || null)}
      />
      <ChipRow
        chips={channelChips}
        selected={list.channelFilter ?? ''}
        onSelect={(id) => list.setChannelFilter(id || null)}
      />
      <ChipRow
        chips={[
          { id: 'all', labelKey: 'reqAssigneeAll' },
          { id: 'me', labelKey: 'reqAssigneeMe' },
        ]}
        selected={list.assigneeFilter}
        onSelect={(id) => list.setAssigneeFilter(id === 'me' ? 'me' : 'all')}
      />
      <ChipRow
        chips={DATE_CHIPS}
        selected={list.datePreset}
        onSelect={(id) => list.setDatePreset((id as DatePreset) || 'all')}
      />

      <FlatList
        data={list.items}
        keyExtractor={(item) => item.request_id}
        renderItem={({ item }) => <RequestCardRow item={item} onPress={() => onOpen(item)} />}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={list.refreshing} onRefresh={() => void list.refresh()} tintColor={colors.accent} />
        }
        onEndReached={() => void list.loadMore()}
        onEndReachedThreshold={0.4}
        ListEmptyComponent={<EmptyState title={tr('reqEmptyTitle')} body={tr('reqEmptyBody')} />}
        ListFooterComponent={
          list.loadingMore ? <ActivityIndicator color={colors.accent} style={{ marginVertical: 12 }} /> : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  centerPad: { flex: 1, justifyContent: 'center', padding: spacing.xl, gap: spacing.md },
  setup: { marginHorizontal: spacing.lg, marginBottom: spacing.md, borderWidth: 1, borderRadius: radii.lg, padding: spacing.lg },
  setupTitle: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  setupBody: { fontFamily: fonts.body, fontSize: 13, marginTop: 6, marginBottom: spacing.md },
  setupBtn: { alignSelf: 'flex-start' },
  counters: { paddingHorizontal: spacing.lg, gap: spacing.sm, paddingBottom: spacing.sm },
  counter: { minWidth: 72, borderRadius: radii.md, borderWidth: 1, paddingVertical: spacing.sm, paddingHorizontal: spacing.md },
  counterN: { fontFamily: fonts.bodyMedium, fontSize: 18 },
  counterL: { fontFamily: fonts.body, fontSize: 11, marginTop: 2 },
  searchWrap: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderRadius: radii.md,
    minHeight: HIT - 4,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  search: { flex: 1, fontFamily: fonts.body, fontSize: 15, paddingVertical: 8 },
  chips: { paddingHorizontal: spacing.lg, gap: 8, paddingBottom: spacing.sm },
  chip: { borderWidth: 1, borderRadius: radii.pill, paddingHorizontal: 12, paddingVertical: 6 },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl, flexGrow: 1 },
});
