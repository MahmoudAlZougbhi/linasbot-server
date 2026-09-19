import { useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { ScreenSkeleton } from '../../components/ScreenSkeleton';
import { useI18n } from '../../i18n/LanguageContext';
import { ScreenChrome } from '../shared/ScreenChrome';
import { ServicesScreen } from '../services/ServicesScreen';
import { AiBasicsScreen } from './aiBasics/AiBasicsScreen';
import { CommentsScreen } from './comments/CommentsScreen';
import { cmFormStyles } from './cmFormStyles';
import type { CmProposalReview } from './cmProposalReview';
import { getCmSection, type CmSectionId } from './cmSections';
import { ArticlesEditor } from './editors/ArticlesEditor';
import { AiLimitsEditor } from './editors/AiLimitsEditor';
import { HandoffEditor } from './editors/HandoffEditor';
import { OffDaysEditor } from './editors/OffDaysEditor';
import { OpeningHoursEditor } from './editors/OpeningHoursEditor';
import { RestrictedEditor } from './editors/PolicyEditors';
import { KnowledgeScreen } from './knowledge/KnowledgeScreen';
import { LocationHoursSectionScreen } from './LocationHoursSectionScreen';
import { RequestRulesScreen } from './requestRules/RequestRulesScreen';
import { SolBasicsScreen } from './sol/SolBasicsScreen';
import { useCmDraft } from './useCmDraft';

type Props = {
  section: CmSectionId;
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
  onOpenLocations?: () => void;
};

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
    case 'care':
      return <ArticlesEditor section="care" payload={payload} onChange={onChange} />;
    case 'handoff':
      return <HandoffEditor payload={payload} onChange={onChange} />;
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
  if (section === 'sol_app_knowledge') {
    return (
      <KnowledgeScreen
        section="sol_app_knowledge"
        proposalReview={proposalReview}
        onBack={onBack}
      />
    );
  }
  if (section === 'sol_basics') {
    return <SolBasicsScreen proposalReview={proposalReview} onBack={onBack} />;
  }
  if (section === 'comments') {
    return <CommentsScreen proposalReview={proposalReview} onBack={onBack} />;
  }
  if (section === 'requests_appointments') {
    return <RequestRulesScreen proposalReview={proposalReview} onBack={onBack} />;
  }
  if (section === 'ai_basics' || section === 'style' || section === 'dynamic_messages') {
    return <AiBasicsScreen proposalReview={proposalReview} onBack={onBack} />;
  }
  if (section === 'prices') {
    return <ServicesScreen proposalReview={proposalReview} onBack={onBack} />;
  }
  if (section === 'branches') {
    return <LocationHoursSectionScreen proposalReview={proposalReview} onBack={onBack} />;
  }
  return (
    <StandardCmSectionScreen section={section} proposalReview={proposalReview} onBack={onBack} />
  );
}

function StandardCmSectionScreen({ section, proposalReview, onBack }: Props) {
  const meta = getCmSection(section);
  const draft = useCmDraft(section, proposalReview);
  const { tr } = useI18n();
  const [savedFlash, setSavedFlash] = useState(false);
  const isAiLimits = section === 'ai_limits';
  const isLanguagesRemoved = section === 'languages';

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
  const subtitle = isAiLimits ? tr('aiLimitsSubtitle') : meta?.description;

  return (
    <ScreenChrome title={title} subtitle={subtitle} sectionTitle={isAiLimits} onBack={onBack}>
      {draft.loading ? <ScreenSkeleton variant="form" /> : null}
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
