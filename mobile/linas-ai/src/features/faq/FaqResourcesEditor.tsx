import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import type { StringKey } from '../../i18n';
import { colors, fonts, spacing } from '../../theme';
import type { KnowledgeAttachment } from '../cm/knowledge/knowledgeModel';
import { KnowledgeResourceGrid, KnowledgeResourceRows } from '../cm/knowledge/KnowledgeResources';
import { ResourceMetaModal } from '../cm/resources/ResourceMetaModal';
import { parseFaqAttachments, serializeFaqAttachments } from './faqAttachments';
import { putFaqAttachments, type FaqGroup } from './faqApi';
import { useFaqMedia } from './useFaqMedia';

type Props = {
  group: FaqGroup;
  onUpdated: (group: FaqGroup) => void;
  tr: (key: StringKey) => string;
};

export function FaqResourcesEditor({ group, onUpdated, tr }: Props) {
  const [attachments, setAttachments] = useState<KnowledgeAttachment[]>(() => parseFaqAttachments(group));
  const [saveError, setSaveError] = useState<string | null>(null);

  async function persist(next: KnowledgeAttachment[]) {
    setAttachments(next);
    setSaveError(null);
    try {
      const data = await putFaqAttachments(group.qa_group_id, serializeFaqAttachments(next));
      onUpdated({ ...group, ...data });
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : tr('faqCreateError'));
      setAttachments(parseFaqAttachments(group));
    }
  }

  const media = useFaqMedia(attachments, (next) => void persist(next), tr);

  return (
    <View style={styles.wrap}>
      <Text style={styles.section}>{tr('knowledgeResources')}</Text>
      <Text style={styles.hint}>{tr('knowledgeResourcesHint')}</Text>
      <KnowledgeResourceGrid onAdd={(kind) => void media.addResource(kind)} tr={tr} />
      {media.uploading ? <Text style={styles.hint}>{tr('productsUploading')}</Text> : null}
      {media.uploadError ? <Text style={styles.error}>{media.uploadError}</Text> : null}
      {saveError ? <Text style={styles.error}>{saveError}</Text> : null}
      <KnowledgeResourceRows
        attachments={attachments}
        onRemove={(id) => void persist(attachments.filter((row) => row.id !== id))}
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
        cancelLabel={tr('usersCancel')}
        onChangeUrl={(url) => media.setPrompt((row) => (row ? { ...row, url } : row))}
        onChangeTitle={(title) => media.setPrompt((row) => (row ? { ...row, title } : row))}
        onChangeDescription={(description) => media.setPrompt((row) => (row ? { ...row, description } : row))}
        onSave={media.commitPrompt}
        onClose={media.closePrompt}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  section: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  hint: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, fontFamily: fonts.body, fontSize: 12 },
});
