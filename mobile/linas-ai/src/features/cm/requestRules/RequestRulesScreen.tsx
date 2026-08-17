import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather } from '../../../components/AppIcon';
import { LinasLoadingIndicator } from '../../../components/LinasLoadingIndicator';
import { PrimaryButton } from '../../../components/PrimaryButton';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts } from '../../../theme';
import { ScreenChrome } from '../../shared/ScreenChrome';
import { asRecordList, newId } from '../cmApi';
import type { CmProposalReview } from '../cmProposalReview';
import { useCmDraft } from '../useCmDraft';
import { RequestRuleEditView } from './RequestRuleEditView';
import { RequestRuleListView } from './RequestRuleListView';
import {
  deleteRequestGraph,
  listRequestGraphs,
  previewRequestGraph,
  publishRequestGraph,
} from './requestGraphsApi';
import { RQ_CANVAS, RQ_TEAL } from './requestRuleChrome';
import {
  createRequestRule,
  destinationFromType,
  matchesRequestQuery,
  parseRequestRule,
  ruleToRecord,
  type RequestGraphRow,
  type RequestRuleItem,
} from './requestRuleModel';

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
};

export function RequestRulesScreen({ proposalReview, onBack }: Props) {
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const draft = useCmDraft('requests_appointments', proposalReview);
  const [mode, setMode] = useState<'list' | 'edit'>('list');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [graphs, setGraphs] = useState<RequestGraphRow[]>([]);
  const [preview, setPreview] = useState<RequestGraphRow | undefined>(undefined);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);

  const items = useMemo(
    () => asRecordList(draft.payload.rules).map(parseRequestRule),
    [draft.payload.rules],
  );
  const selected = items.find((item) => item.id === selectedId) || null;
  const visible = useMemo(
    () => items.filter((item) => matchesRequestQuery(item, query)),
    [items, query],
  );
  const graphsBySource = useMemo(() => {
    const map: Record<string, RequestGraphRow> = {};
    for (const row of graphs) {
      if (row.source_item_id) map[row.source_item_id] = row;
    }
    return map;
  }, [graphs]);

  const loadGraphs = useCallback(async () => {
    try {
      setGraphs(await listRequestGraphs());
      setGraphError(null);
    } catch {
      setGraphError(tr('requestRulesGraphLoadFailed'));
    }
  }, [tr]);

  useEffect(() => {
    void loadGraphs();
  }, [loadGraphs]);

  function setRules(next: RequestRuleItem[]) {
    draft.setPayload({ ...draft.payload, rules: next.map(ruleToRecord) });
  }

  function patchSelected(patch: Partial<RequestRuleItem>) {
    if (!selected) return;
    setRules(items.map((item) => (item.id === selected.id ? { ...item, ...patch } : item)));
  }

  function handleAdd() {
    const item = createRequestRule(newId('req'));
    setRules([item, ...items]);
    setSelectedId(item.id);
    setPreview(undefined);
    setSaveError(null);
    setMode('edit');
  }

  function goList() {
    if (selected && !selected.name.trim() && !selected.notes.trim()) {
      setRules(items.filter((item) => item.id !== selected.id));
    }
    setMode('list');
    setSelectedId(null);
    setPreview(undefined);
    setSaveError(null);
  }

  async function handlePreview() {
    if (!selected) return;
    try {
      const row = await previewRequestGraph({
        title: selected.name,
        source_text: `${selected.name}\n${selected.notes}`.trim(),
        destination: destinationFromType(selected.type),
      });
      setPreview(row);
      setSaveError(row.status === 'draft' ? tr('aiSetupRequestNeedsClarification') : null);
    } catch {
      setSaveError(tr('requestRulesPreviewFailed'));
    }
  }

  async function handleSave() {
    if (!selected?.name.trim()) {
      setSaveError(tr('requestRulesNameRequired'));
      return;
    }
    const ok = await draft.save();
    if (!ok) return;
    try {
      const graph = await publishRequestGraph({
        source_item_id: selected.id,
        title: selected.name,
        source_text: `${selected.name}\n${selected.notes}`.trim(),
        destination: destinationFromType(selected.type),
        confirm: true,
      });
      if (graph.status !== 'active') {
        setPreview(graph);
        setSaveError(tr('aiSetupRequestNeedsClarification'));
        await loadGraphs();
        return;
      }
      await loadGraphs();
      goList();
    } catch {
      setSaveError(tr('requestRulesPublishFailed'));
    }
  }

  function confirmDelete() {
    if (!selected) return;
    Alert.alert(tr('requestRulesDeleteTitle'), tr('requestRulesDeleteBody'), [
      { text: tr('usersCancel'), style: 'cancel' },
      {
        text: tr('aiSetupDeleteRequest'),
        style: 'destructive',
        onPress: () => {
          void (async () => {
            const definitionId = graphsBySource[selected.id]?.definition_id;
            const nextPayload = {
              ...draft.payload,
              rules: items.filter((item) => item.id !== selected.id).map(ruleToRecord),
            };
            const ok = await draft.save(nextPayload);
            if (!ok) return;
            if (definitionId) {
              try {
                await deleteRequestGraph(definitionId);
              } catch {
                setSaveError(tr('requestRulesDeleteGraphFailed'));
              }
            }
            await loadGraphs();
            goList();
          })();
        },
      },
    ]);
  }

  return (
    <ScreenChrome
      title={tr('aiSetupSec_requests_appointments')}
      subtitle={mode === 'list' ? tr('requestRulesSubtitle') : undefined}
      onBack={mode === 'list' ? onBack : goList}
      canvasColor={RQ_CANVAS}
    >
      {draft.loading ? <LinasLoadingIndicator variant="screen" /> : null}
      {draft.error ? <Text style={styles.error}>{draft.error}</Text> : null}
      {draft.conflict ? <Text style={styles.warn}>{draft.conflict}</Text> : null}
      {graphError && mode === 'list' ? <Text style={styles.warn}>{graphError}</Text> : null}

      {!draft.loading && mode === 'list' ? (
        <ScrollView contentContainerStyle={styles.listScroll} showsVerticalScrollIndicator={false}>
          <RequestRuleListView
            items={visible}
            graphsBySource={graphsBySource}
            query={query}
            onQueryChange={setQuery}
            onAdd={handleAdd}
            onSelect={(id) => {
              setSelectedId(id);
              setPreview(undefined);
              setMode('edit');
            }}
            tr={tr}
          />
        </ScrollView>
      ) : null}

      {!draft.loading && mode === 'edit' && selected ? (
        <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={styles.editScroll} showsVerticalScrollIndicator={false}>
            {saveError ? <Text style={styles.error}>{saveError}</Text> : null}
            <RequestRuleEditView
              item={selected}
              graph={graphsBySource[selected.id]}
              preview={preview}
              onTitle={(name) => patchSelected({ name })}
              onType={(type) => patchSelected({ type })}
              onNote={(notes) => patchSelected({ notes })}
              onPreview={() => void handlePreview()}
              tr={tr}
            />
          </ScrollView>
          <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 12) }]}>
            <Pressable
              onPress={confirmDelete}
              accessibilityRole="button"
              accessibilityLabel={tr('aiSetupDeleteRequest')}
              style={({ pressed }) => [styles.deleteBtn, pressed && styles.pressed]}
            >
              <AppIcon icon={feather('trash-2')} size={18} color="#DC2626" />
              <Text style={styles.deleteText}>{tr('aiSetupDeleteRequest')}</Text>
            </Pressable>
            <PrimaryButton
              label={tr('requestRulesSave')}
              onPress={() => void handleSave()}
              loading={draft.saving}
              disabled={!draft.etag}
              style={styles.saveBtn}
            />
          </View>
        </KeyboardAvoidingView>
      ) : null}
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  listScroll: { flexGrow: 1, paddingBottom: 16 },
  editScroll: { paddingBottom: 16 },
  error: { color: '#DC2626', fontFamily: fonts.body, marginBottom: 8 },
  warn: { color: '#D97706', fontFamily: fonts.body, marginBottom: 8 },
  footer: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingTop: 8 },
  deleteBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderWidth: 1.5,
    borderColor: '#DC2626',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    minWidth: 108,
  },
  deleteText: { color: '#DC2626', fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  saveBtn: { flex: 1, backgroundColor: RQ_TEAL, borderRadius: 12 },
  pressed: { opacity: 0.7 },
});
