import { useState } from 'react';
import { ActivityIndicator, ScrollView, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { colors } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import type { CmProposalReview } from './cmProposalReview';
import { cmFormStyles } from './cmFormStyles';
import { getCmSection, type CmSectionId } from './cmSections';
import { AiBasicsEditor } from './editors/AiBasicsEditor';
import { ArticlesEditor } from './editors/ArticlesEditor';
import { BranchesEditor } from './editors/BranchesEditor';
import { DynamicMessagesEditor } from './editors/DynamicMessagesEditor';
import { HandoffEditor } from './editors/HandoffEditor';
import { LanguagesEditor } from './editors/LanguagesEditor';
import { OffDaysEditor } from './editors/OffDaysEditor';
import { OpeningHoursEditor } from './editors/OpeningHoursEditor';
import { ActionsEditor, AiLimitsEditor, RestrictedEditor } from './editors/PolicyEditors';
import { CommentsEditor } from './editors/CommentsEditor';
import { PricesEditor } from './editors/PricesEditor';
import { RequestsAppointmentsEditor } from './editors/RequestsAppointmentsEditor';
import { ServicesEditor } from './editors/ServicesEditor';
import { StyleEditor } from './editors/StyleEditor';
import { useCmDraft } from './useCmDraft';

type Props = {
  section: CmSectionId;
  /** Local overlay of a chat proposal — shown dirty, not auto-saved. */
  proposalReview?: CmProposalReview | null;
};

function SectionBody({
  section,
  payload,
  onChange,
}: {
  section: CmSectionId;
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  switch (section) {
    case 'ai_basics':
      return <AiBasicsEditor payload={payload} onChange={onChange} />;
    case 'languages':
      return <LanguagesEditor payload={payload} onChange={onChange} />;
    case 'style':
      return <StyleEditor payload={payload} onChange={onChange} />;
    case 'services':
      return <ServicesEditor payload={payload} onChange={onChange} />;
    case 'prices':
      return <PricesEditor payload={payload} onChange={onChange} />;
    case 'knowledge':
      return <ArticlesEditor section="knowledge" payload={payload} onChange={onChange} />;
    case 'care':
      return <ArticlesEditor section="care" payload={payload} onChange={onChange} />;
    case 'handoff':
      return <HandoffEditor payload={payload} onChange={onChange} />;
    case 'dynamic_messages':
      return <DynamicMessagesEditor payload={payload} onChange={onChange} />;
    case 'branches':
      return <BranchesEditor payload={payload} onChange={onChange} />;
    case 'opening_hours':
      return <OpeningHoursEditor payload={payload} onChange={onChange} />;
    case 'restricted':
      return <RestrictedEditor payload={payload} onChange={onChange} />;
    case 'comments':
      return <CommentsEditor payload={payload} onChange={onChange} />;
    case 'actions':
      return <ActionsEditor payload={payload} onChange={onChange} />;
    case 'ai_limits':
      return <AiLimitsEditor payload={payload} onChange={onChange} />;
    case 'off_days':
      return <OffDaysEditor payload={payload} onChange={onChange} />;
    case 'requests_appointments':
      return <RequestsAppointmentsEditor payload={payload} onChange={onChange} />;
    default:
      return <Text style={cmFormStyles.error}>Unknown section.</Text>;
  }
}

export function CmSectionScreen({ section, proposalReview }: Props) {
  const meta = getCmSection(section);
  const draft = useCmDraft(section, proposalReview);
  const [savedFlash, setSavedFlash] = useState(false);

  async function handleSave() {
    const ok = await draft.save();
    if (ok) {
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
    }
  }

  return (
    <ScreenChrome title={meta?.title ?? section} subtitle={meta?.description}>
      {draft.loading ? <ActivityIndicator color={colors.accent} /> : null}
      {draft.error ? <Text style={cmFormStyles.error}>{draft.error}</Text> : null}
      {draft.conflict ? <Text style={cmFormStyles.warn}>{draft.conflict}</Text> : null}
      {draft.proposalActive ? (
        <Text style={cmFormStyles.warn}>
          AI proposal preview — not saved yet. Approve in chat, or tap Save draft here.
        </Text>
      ) : null}
      {savedFlash ? <Text style={cmFormStyles.ok}>Draft saved.</Text> : null}
      {!draft.loading ? (
        <ScrollView contentContainerStyle={{ paddingBottom: 48 }}>
          <SectionBody section={section} payload={draft.payload} onChange={draft.setPayload} />
          <View style={cmFormStyles.actions}>
            <PrimaryButton
              label={draft.dirty ? 'Save draft' : 'Saved'}
              onPress={() => void handleSave()}
              loading={draft.saving}
              disabled={!draft.dirty || !draft.etag}
              style={{ flex: 1 }}
            />
            <PrimaryButton
              label="Reload"
              variant="ghost"
              onPress={() => void draft.load()}
              style={{ flex: 1 }}
            />
          </View>
        </ScrollView>
      ) : null}
    </ScreenChrome>
  );
}
