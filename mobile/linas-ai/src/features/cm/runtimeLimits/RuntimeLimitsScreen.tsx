import { useState } from 'react';
import { ScrollView, Text, TextInput, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { ScreenSkeleton } from '../../../components/ScreenSkeleton';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts } from '../../../theme';
import { ScreenChrome } from '../../shared/ScreenChrome';
import type { CmProposalReview } from '../cmProposalReview';
import { cmFormStyles } from '../cmFormStyles';
import { useCmDraft } from '../useCmDraft';

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
};

const DEFAULTS: Record<string, number> = {
  owner_history_messages: 100,
  owner_message_max_chars: 0,
  customer_history_messages: 50,
  customer_message_max_chars: 600,
  product_search_cap: 24,
  catalog_evidence_cap: 18,
  max_retrieval_rounds: 3,
  max_agent_steps: 6,
  max_tool_calls: 8,
};

function num(payload: Record<string, unknown>, key: string): string {
  const fallback = DEFAULTS[key] ?? 0;
  const raw = payload[key];
  if (raw === undefined || raw === null || raw === '') return String(fallback);
  const n = Number(raw);
  return String(Number.isFinite(n) ? n : fallback);
}

function LimitField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={cmFormStyles.label}>{label}</Text>
      {hint ? <Text style={cmFormStyles.hint}>{hint}</Text> : null}
      <TextInput
        value={value}
        onChangeText={onChange}
        keyboardType="number-pad"
        style={{
          borderWidth: 1,
          borderColor: '#D5DEDC',
          borderRadius: 10,
          paddingHorizontal: 12,
          paddingVertical: 10,
          fontFamily: fonts.body,
          fontSize: 16,
          color: '#000',
        }}
      />
    </View>
  );
}

export function RuntimeLimitsScreen({ proposalReview, onBack }: Props) {
  const { tr } = useI18n();
  const draft = useCmDraft('runtime_limits', proposalReview);
  const [savedFlash, setSavedFlash] = useState(false);
  const payload = draft.payload;

  function setNum(key: string, value: string) {
    const n = Number(value.replace(/[^\d]/g, ''));
    draft.setPayload({ ...payload, [key]: Number.isFinite(n) ? n : 0 });
  }

  async function handleSave() {
    const ok = await draft.save();
    if (ok) {
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
    }
  }

  return (
    <ScreenChrome title={tr('aiSetupSec_runtime_limits')} subtitle={tr('runtimeLimitsSubtitle')} onBack={onBack}>
      {draft.loading ? <ScreenSkeleton variant="form" /> : null}
      {draft.error ? <Text style={cmFormStyles.error}>{draft.error}</Text> : null}
      {savedFlash ? <Text style={cmFormStyles.ok}>{tr('runtimeLimitsSavedLive')}</Text> : null}
      <ScrollView>
        <View style={cmFormStyles.card}>
          <Text style={cmFormStyles.rowTitle}>{tr('runtimeLimitsCustomerTitle')}</Text>
          <Text style={cmFormStyles.hint}>{tr('runtimeLimitsCustomerHint')}</Text>
          <LimitField
            label={tr('runtimeLimitsCustomerHistory')}
            value={num(payload, 'customer_history_messages')}
            onChange={(v) => setNum('customer_history_messages', v)}
          />
          <LimitField
            label={tr('runtimeLimitsCustomerChars')}
            hint={tr('runtimeLimitsCharsHint')}
            value={num(payload, 'customer_message_max_chars')}
            onChange={(v) => setNum('customer_message_max_chars', v)}
          />
          <LimitField
            label={tr('runtimeLimitsProductCap')}
            value={num(payload, 'product_search_cap')}
            onChange={(v) => setNum('product_search_cap', v)}
          />
          <LimitField
            label={tr('runtimeLimitsCatalogCap')}
            value={num(payload, 'catalog_evidence_cap')}
            onChange={(v) => setNum('catalog_evidence_cap', v)}
          />
          <LimitField
            label={tr('runtimeLimitsRetrievalRounds')}
            value={num(payload, 'max_retrieval_rounds')}
            onChange={(v) => setNum('max_retrieval_rounds', v)}
          />
          <LimitField
            label={tr('runtimeLimitsAgentSteps')}
            value={num(payload, 'max_agent_steps')}
            onChange={(v) => setNum('max_agent_steps', v)}
          />
          <LimitField
            label={tr('runtimeLimitsToolCalls')}
            value={num(payload, 'max_tool_calls')}
            onChange={(v) => setNum('max_tool_calls', v)}
          />
        </View>
        <View style={cmFormStyles.card}>
          <Text style={cmFormStyles.rowTitle}>{tr('runtimeLimitsSolTitle')}</Text>
          <Text style={cmFormStyles.hint}>{tr('runtimeLimitsSolHint')}</Text>
          <LimitField
            label={tr('runtimeLimitsOwnerHistory')}
            value={num(payload, 'owner_history_messages')}
            onChange={(v) => setNum('owner_history_messages', v)}
          />
          <LimitField
            label={tr('runtimeLimitsOwnerChars')}
            hint={tr('runtimeLimitsOwnerCharsHint')}
            value={num(payload, 'owner_message_max_chars')}
            onChange={(v) => setNum('owner_message_max_chars', v)}
          />
        </View>
        <PrimaryButton
          label={tr('runtimeLimitsSave')}
          onPress={() => void handleSave()}
          disabled={!draft.dirty || draft.saving}
        />
      </ScrollView>
    </ScreenChrome>
  );
}
