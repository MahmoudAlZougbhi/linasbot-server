import { ActivityIndicator, Text, View } from 'react-native';

import { useI18n } from '../../../../i18n/LanguageContext';
import { useFaqMedia } from '../../../faq/useFaqMedia';
import type { KnowledgeAttachment } from '../../knowledge/knowledgeModel';
import { KnowledgeResourceGrid, KnowledgeResourceRows } from '../../knowledge/KnowledgeResources';
import { ResourceMetaModal } from '../../resources/ResourceMetaModal';
import { asBranchAttachments, type BranchAttachment } from './branchMedia';
import { locStyles, locTeal } from './locationHoursStyles';

type Props = {
  attachments: unknown;
  onAttachments: (next: BranchAttachment[]) => void;
};

function toKnowledge(value: unknown): KnowledgeAttachment[] {
  return asBranchAttachments(value).map((row) => ({ ...row, duration_seconds: null }));
}

function toBranch(rows: KnowledgeAttachment[]): BranchAttachment[] {
  return rows.map(({ duration_seconds: _d, ...row }) => row);
}

export function BranchMediaSection({ attachments, onAttachments }: Props) {
  const { tr } = useI18n();
  const rows = toKnowledge(attachments);
  const persist = (next: KnowledgeAttachment[]) => onAttachments(toBranch(next));
  const media = useFaqMedia(rows, persist, tr);

  return (
    <View>
      <Text style={locStyles.sectionTitle}>{tr('knowledgeResources')}</Text>
      <Text style={locStyles.sectionHint}>{tr('knowledgeResourcesHint')}</Text>
      <KnowledgeResourceGrid onAdd={(kind) => void media.addResource(kind)} tr={tr} />
      {media.uploading ? <ActivityIndicator color={locTeal} style={{ marginBottom: 8 }} /> : null}
      {media.uploadError ? <Text style={locStyles.error}>{media.uploadError}</Text> : null}
      <KnowledgeResourceRows
        attachments={rows}
        onRemove={(id) => persist(rows.filter((row) => row.id !== id))}
        onReplace={(att) => void media.addResource(att.kind, att.id)}
        onEditCaption={media.editResource}
        tr={tr}
      />
      <ResourceMetaModal
        visible={Boolean(media.prompt)}
        heading={media.prompt?.kind === 'link' ? tr('knowledgeLinkTitle') : tr('resourceMetaHeading')}
        preview={media.prompt?.preview}
        showUrl={media.prompt?.kind === 'link'}
        url={media.prompt?.url || ''}
        title={media.prompt?.title || ''}
        description={media.prompt?.description || ''}
        error={media.promptError}
        titleLabel={tr('resourceFieldTitle')}
        descriptionLabel={tr('resourceFieldDescription')}
        urlLabel={tr('knowledgeLinkTitle')}
        titlePlaceholder={tr('resourceTitlePlaceholder')}
        descriptionPlaceholder={tr('resourceDescriptionPlaceholder')}
        urlPlaceholder={tr('knowledgeLinkPlaceholder')}
        saveLabel={tr('aiSetupSave')}
        cancelLabel={tr('aiSetupLocCancel')}
        onChangeUrl={(url) => media.setPrompt((row) => (row ? { ...row, url } : row))}
        onChangeTitle={(title) => media.setPrompt((row) => (row ? { ...row, title } : row))}
        onChangeDescription={(description) => media.setPrompt((row) => (row ? { ...row, description } : row))}
        onSave={media.commitPrompt}
        onClose={media.closePrompt}
      />
    </View>
  );
}
