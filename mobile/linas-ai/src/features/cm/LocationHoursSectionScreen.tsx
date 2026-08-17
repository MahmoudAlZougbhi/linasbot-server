import { useState } from 'react';
import { Alert, Text } from 'react-native';

import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { useI18n } from '../../i18n/LanguageContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { asRecordList, newId, primaryLabel } from './cmApi';
import { isDraftDirty, stableSerialize } from './cmDraftDirty';
import { cmFormStyles } from './cmFormStyles';
import type { CmProposalReview } from './cmProposalReview';
import { BranchEditView } from './editors/locationOpeningHours/BranchEditView';
import { BranchListView } from './editors/locationOpeningHours/BranchListView';
import { newBranchRecord } from './editors/locationOpeningHours/branchScheduleHelpers';
import { useCmDraft } from './useCmDraft';

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
};

type Tab = 'details' | 'hours';

export function LocationHoursSectionScreen({ proposalReview, onBack }: Props) {
  const { tr } = useI18n();
  const draft = useCmDraft('branches', proposalReview);
  const items = asRecordList(draft.payload.items);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('details');
  const [query, setQuery] = useState('');
  const selected = items.find((item) => String(item.id) === selectedId) || null;

  const setItems = (next: Record<string, unknown>[]) => {
    const nextPayload = { ...draft.payload, items: next };
    if (!isDraftDirty(stableSerialize(draft.payload), nextPayload)) return;
    draft.setPayload(nextPayload);
  };

  const patchBranch = (id: string, data: Record<string, unknown>) => {
    setItems(items.map((item) => (String(item.id) === id ? { ...item, ...data } : item)));
  };

  const addBranch = () => {
    const id = newId('branch');
    setItems([newBranchRecord(id), ...items]);
    setSelectedId(id);
    setTab('details');
  };

  const handleBack = () => {
    if (selected) {
      setSelectedId(null);
      setTab('details');
      return;
    }
    if (!draft.hasUnsavedChanges()) {
      onBack?.();
      return;
    }
    Alert.alert(tr('aiSetupLocUnsavedTitle'), tr('aiSetupLocUnsavedBody'), [
      { text: tr('aiSetupLocDiscard'), style: 'destructive', onPress: () => onBack?.() },
      {
        text: tr('aiSetupLocSaveChanges'),
        onPress: () => {
          void draft.save().then((ok) => {
            if (ok) onBack?.();
          });
        },
      },
      { text: tr('aiSetupLocCancel'), style: 'cancel' },
    ]);
  };

  const save = (requireName: boolean) => {
    if (requireName && selected && !primaryLabel(selected.labels).trim()) {
      Alert.alert(tr('aiSetupLocNameRequired'));
      return;
    }
    if (!draft.dirty) return;
    void draft.save();
  };

  const deleteBranch = () => {
    if (!selected) return;
    Alert.alert(tr('aiSetupLocDeleteConfirmTitle'), tr('aiSetupLocDeleteConfirmBody'), [
      { text: tr('aiSetupLocCancel'), style: 'cancel' },
      {
        text: tr('aiSetupLocDeleteBranch'),
        style: 'destructive',
        onPress: () => {
          const nextPayload = {
            ...draft.payload,
            items: items.filter((item) => String(item.id) !== String(selected.id)),
          };
          draft.setPayload(nextPayload);
          setSelectedId(null);
          void draft.save(nextPayload);
        },
      },
    ]);
  };

  return (
    <ScreenChrome
      title={tr('aiSetupSec_branches')}
      subtitle={!selected ? tr('aiSetupLocSubtitle') : undefined}
      onBack={handleBack}
    >
      {draft.loading ? <LinasLoadingIndicator variant="screen" /> : null}
      {draft.error ? <Text style={cmFormStyles.error}>{draft.error}</Text> : null}
      {draft.conflict ? <Text style={cmFormStyles.warn}>{draft.conflict}</Text> : null}
      {!draft.loading && !selected ? (
        <BranchListView
          items={items}
          query={query}
          onQuery={setQuery}
          onAdd={addBranch}
          onOpen={setSelectedId}
        />
      ) : null}
      {!draft.loading && selected ? (
        <BranchEditView
          branch={selected}
          tab={tab}
          onTab={setTab}
          onPatch={(data) => patchBranch(String(selected.id), data)}
          onSave={() => save(tab === 'details')}
          onDelete={deleteBranch}
          saving={draft.saving}
          canSave={Boolean(draft.etag)}
        />
      ) : null}
    </ScreenChrome>
  );
}
