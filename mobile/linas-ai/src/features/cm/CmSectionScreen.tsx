import { useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import type { CmProposalReview } from './cmProposalReview';
import { cmFormStyles } from './cmFormStyles';
import { getCmSection, type CmSectionId } from './cmSections';
import { AiBasicsEditor } from './editors/AiBasicsEditor';
import { ArticlesEditor } from './editors/ArticlesEditor';
import { KnowledgeScreen } from './knowledge/KnowledgeScreen';
import { LocationHoursSectionScreen } from './LocationHoursSectionScreen';
import { CommentsScreen } from './comments/CommentsScreen';
import { RequestRulesScreen } from './requestRules/RequestRulesScreen';
import { OpeningHoursEditor } from './editors/OpeningHoursEditor';
import { GreetingsEditor } from './editors/GreetingsEditor';
import { HandoffEditor } from './editors/HandoffEditor';
import { OffDaysEditor } from './editors/OffDaysEditor';
import { AiLimitsEditor } from './editors/AiLimitsEditor';
import { RestrictedEditor } from './editors/PolicyEditors';
import { PricesEditor } from './editors/PricesEditor';
import { ServicesEditor } from './editors/ServicesEditor';
import { useCmDraft } from './useCmDraft';
import { useCmMultiDraft } from './useCmMultiDraft';

type Props = {
  section: CmSectionId;
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
  onOpenLocations?: () => void;
};

function AiBasicsComposite({ proposalReview }: { proposalReview?: CmProposalReview | null }) {
  const { tr } = useI18n();
  const multi = useCmMultiDraft(['ai_basics', 'style', 'dynamic_messages'], proposalReview);
  const basics = multi.drafts.ai_basics?.payload ?? {};
  const style = multi.drafts.style?.payload ?? {};
  const greetings = multi.drafts.dynamic_messages?.payload ?? {};

  return (
    <>
      {multi.loading ? <LinasLoadingIndicator variant="screen" /> : null}
      {multi.error ? <Text style={cmFormStyles.error}>{multi.error}</Text> : null}
      {multi.conflict ? <Text style={cmFormStyles.warn}>{multi.conflict}</Text> : null}
      {!multi.loading ? (
        <AiBasicsEditor
          basicsPayload={basics}
          stylePayload={style}
          greetingsPayload={greetings}
          onBasicsChange={(next) => multi.setPayload('ai_basics', next)}
          onStyleChange={(next) => multi.setPayload('style', next)}
          onGreetingsChange={(next) => multi.setPayload('dynamic_messages', next)}
        />
      ) : null}
      {!multi.loading ? (
        <View style={cmFormStyles.actions}>
          <PrimaryButton
            label={multi.dirty ? tr('aiSetupSaveDraft') : tr('aiSetupSaved')}
            onPress={() => void multi.save()}
            loading={multi.saving}
            disabled={!multi.dirty || !multi.canSave}
            style={{ flex: 1 }}
          />
          <PrimaryButton
            label={tr('aiSetupReload')}
            variant="ghost"
            onPress={() => void multi.load()}
            style={{ flex: 1 }}
          />
        </View>
      ) : null}
    </>
  );
}

function SectionBody({
  section,
  payload,
  onChange,
  onSave,
  saving,
  dirty,
  canSave,
}: {
  section: CmSectionId;
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  onSave?: () => void;
  saving?: boolean;
  dirty?: boolean;
  canSave?: boolean;
}) {
  switch (section) {
    case 'services':
      return <ServicesEditor payload={payload} onChange={onChange} />;
    case 'prices':
      return <PricesEditor payload={payload} onChange={onChange} />;
    case 'care':
      return <ArticlesEditor section="care" payload={payload} onChange={onChange} />;
    case 'handoff':
      return <HandoffEditor payload={payload} onChange={onChange} />;
    case 'dynamic_messages':
      return <GreetingsEditor payload={payload} onChange={onChange} />;
    case 'branches':
      return null;
    case 'opening_hours':
      return <OpeningHoursEditor payload={payload} onChange={onChange} />;
    case 'restricted':
      return <RestrictedEditor payload={payload} onChange={onChange} />;
    case 'ai_limits':
      return (
        <AiLimitsEditor
          payload={payload}
          onChange={onChange}
          onSave={onSave}
          saving={saving}
          dirty={dirty}
          canSave={canSave}
        />
      );
    case 'off_days':
      return <OffDaysEditor payload={payload} onChange={onChange} />;
    default:
      return <Text style={cmFormStyles.error}>Unknown section.</Text>;
  }
}

export function CmSectionScreen({ section, proposalReview, onBack, onOpenLocations }: Props) {
  if (section === 'knowledge') {
    return (
      <KnowledgeScreen
        proposalReview={proposalReview}
        onBack={onBack}
        onOpenLocations={onOpenLocations}
      />
    );
  }
  if (section === 'comments') {
    return <CommentsScreen proposalReview={proposalReview} onBack={onBack} />;
  }
  if (section === 'requests_appointments') {
    return <RequestRulesScreen proposalReview={proposalReview} onBack={onBack} />;
  }
  if (section === 'ai_basics' || section === 'style' || section === 'dynamic_messages') {
    return (
      <AiBasicsSectionScreen proposalReview={proposalReview} onBack={onBack} />
    );
  }
  if (section === 'branches') {
    return <LocationHoursSectionScreen proposalReview={proposalReview} onBack={onBack} />;
  }
  return (
    <StandardCmSectionScreen section={section} proposalReview={proposalReview} onBack={onBack} />
  );
}

function AiBasicsSectionScreen({
  proposalReview,
  onBack,
}: {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
}) {
  const { tr } = useI18n();
  return (
    <ScreenChrome title={tr('aiSetupSec_ai_basics')} subtitle={tr('aiSetupBasicsSubtitle')} onBack={onBack}>
      <ScrollView contentContainerStyle={{ paddingBottom: 48 }}>
        <AiBasicsComposite proposalReview={proposalReview} />
      </ScrollView>
    </ScreenChrome>
  );
}

function StandardCmSectionScreen({ section, proposalReview, onBack }: Props) {
  const meta = getCmSection(section);
  const draft = useCmDraft(section, proposalReview);
  const { tr } = useI18n();
  const [savedFlash, setSavedFlash] = useState(false);
  const isAiLimits = section === 'ai_limits';
  const isLanguagesRemoved = section === 'languages';
  const isRequests = section === 'requests_appointments';

  async function handleSave() {
    const ok = await draft.save();
    if (ok) {
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
    }
  }

  if (isLanguagesRemoved) {
    return (
      <ScreenChrome title={tr('aiSetupSec_languages')} subtitle={tr('aiSetupLanguagesRemovedBody')} onBack={onBack}>
        <View style={cmFormStyles.card}>
          <Text style={cmFormStyles.hint}>{tr('aiSetupLanguagesRemovedBody')}</Text>
        </View>
      </ScreenChrome>
    );
  }

  const title = isAiLimits ? tr('aiLimitsTitle') : (meta?.title ?? section);
  const subtitle = isAiLimits
    ? tr('aiLimitsSubtitle')
    : isRequests
      ? tr('aiSetupRequestsSubtitle')
      : meta?.description;

  return (
    <ScreenChrome title={title} subtitle={subtitle} sectionTitle={isAiLimits} onBack={onBack}>
      {draft.loading ? <LinasLoadingIndicator variant="screen" /> : null}
      {draft.error ? <Text style={cmFormStyles.error}>{draft.error}</Text> : null}
      {draft.conflict ? <Text style={cmFormStyles.warn}>{draft.conflict}</Text> : null}
      {draft.proposalActive ? (
        <Text style={cmFormStyles.warn}>
          AI proposal preview — not saved yet. Approve in chat, or tap Save draft here.
        </Text>
      ) : null}
      {savedFlash && !isAiLimits ? <Text style={cmFormStyles.ok}>{tr('aiSetupDraftSaved')}</Text> : null}
      {!draft.loading ? (
        <ScrollView contentContainerStyle={{ paddingBottom: 48 }}>
          <SectionBody
            section={section}
            payload={draft.payload}
            onChange={draft.setPayload}
            onSave={() => void handleSave()}
            saving={draft.saving}
            dirty={draft.dirty}
            canSave={Boolean(draft.etag)}
          />
          {isAiLimits ? null : (
            <View style={cmFormStyles.actions}>
              <PrimaryButton
                label={draft.dirty ? tr('aiSetupSaveDraft') : tr('aiSetupSaved')}
                onPress={() => void handleSave()}
                loading={draft.saving}
                disabled={!draft.dirty || !draft.etag}
                style={{ flex: 1 }}
              />
              <PrimaryButton
                label={tr('aiSetupReload')}
                variant="ghost"
                onPress={() => void draft.load()}
                style={{ flex: 1 }}
              />
            </View>
          )}
        </ScrollView>
      ) : null}
    </ScreenChrome>
  );
}
