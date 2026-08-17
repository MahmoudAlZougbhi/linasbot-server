import { useMemo, useState } from 'react';
import {
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
import type { CmProposalReview } from '../cmProposalReview';
import { confirmAiSetupDelete } from '../confirmAiSetupDelete';
import { ResourceMetaModal } from '../resources/ResourceMetaModal';
import { moveById } from '../resources/resourceMeta';
import { useCmMultiDraft } from '../useCmMultiDraft';
import { useKnowledgeMedia } from '../knowledge/useKnowledgeMedia';
import type { KnowledgeItem } from '../knowledge/knowledgeModel';
import { AB_CANVAS, AB_FOREST } from './aiBasicsChrome';
import {
  emptyGreeting,
  greetingToRecord,
  parseGreetings,
  withGreetingNote,
  type GreetingRule,
} from './aiBasicsModel';
import { AiBasicsGreetingsList } from './AiBasicsGreetingsList';
import { AiBasicsIdentityTab } from './AiBasicsIdentityTab';
import { AiBasicsStyleTab } from './AiBasicsStyleTab';
import { AiBasicsTabBar, type AiBasicsTab } from './AiBasicsTabBar';
import { GreetingEditView } from './GreetingEditView';

/** Stable list — inline array would retrigger draft load on every chrome re-render. */
const AI_BASICS_COMPOSITE_SECTIONS = ['ai_basics', 'style', 'dynamic_messages'] as const;

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
};

export function AiBasicsScreen({ proposalReview, onBack }: Props) {
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const multi = useCmMultiDraft(AI_BASICS_COMPOSITE_SECTIONS, proposalReview);
  const [tab, setTab] = useState<AiBasicsTab>('identity');
  const [mode, setMode] = useState<'hub' | 'greeting'>('hub');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isNewGreeting, setIsNewGreeting] = useState(false);
  const [query, setQuery] = useState('');

  const basics = multi.drafts.ai_basics?.payload ?? {};
  const style = multi.drafts.style?.payload ?? {};
  const greetingsPayload = multi.drafts.dynamic_messages?.payload ?? {};
  const items = useMemo(() => parseGreetings(greetingsPayload), [greetingsPayload]);
  const selected = items.find((item) => item.id === selectedId) || null;

  function setGreetings(next: GreetingRule[]) {
    multi.setPayload('dynamic_messages', {
      ...greetingsPayload,
      items: next.map(greetingToRecord),
    });
  }

  function patchGreeting(id: string, patch: Partial<GreetingRule>) {
    setGreetings(items.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  const mediaHost = selected
    ? ({ id: selected.id, attachments: selected.attachments } as KnowledgeItem)
    : null;
  const media = useKnowledgeMedia(
    mediaHost,
    (patch) => {
      if (!selected || !patch.attachments) return;
      patchGreeting(selected.id, { attachments: patch.attachments });
    },
    tr,
  );

  function goHub() {
    setMode('hub');
    setSelectedId(null);
    setIsNewGreeting(false);
    media.setUploadError(null);
  }

  function handleAddGreeting() {
    const item = emptyGreeting();
    setGreetings([item, ...items]);
    setSelectedId(item.id);
    setIsNewGreeting(true);
    setMode('greeting');
    setTab('greetings');
  }

  function openGreeting(id: string) {
    setSelectedId(id);
    setIsNewGreeting(false);
    setMode('greeting');
  }

  async function handleDeleteGreeting(id: string) {
    const nextPayload = {
      ...greetingsPayload,
      items: items.filter((item) => item.id !== id).map(greetingToRecord),
    };
    const ok = await multi.save({ dynamic_messages: nextPayload });
    if (ok && selectedId === id) goHub();
  }

  function confirmDelete(id?: string) {
    const target = id || selectedId;
    if (!target) return;
    confirmAiSetupDelete({
      title: tr('aiSetupGreetingDeleteTitle'),
      body: tr('aiSetupGreetingDeleteBody'),
      confirmLabel: tr('aiSetupDeleteGreeting'),
      cancelLabel: tr('usersCancel'),
      onConfirm: () => void handleDeleteGreeting(target),
    });
  }

  const editingGreeting = mode === 'greeting';
  const chromeTitle = editingGreeting ? tr('aiSetupGreetingsHeading') : tr('aiSetupSec_ai_basics');
  const chromeSubtitle = editingGreeting ? undefined : tr('aiSetupBasicsSubtitle');

  return (
    <ScreenChrome
      title={chromeTitle}
      subtitle={chromeSubtitle}
      onBack={editingGreeting ? goHub : onBack}
      canvasColor={AB_CANVAS}
    >
      {multi.loading ? <LinasLoadingIndicator variant="screen" /> : null}
      {multi.error ? <Text style={styles.error}>{multi.error}</Text> : null}
      {multi.conflict ? <Text style={styles.warn}>{multi.conflict}</Text> : null}

      {!multi.loading && !editingGreeting ? (
        <View style={styles.flex}>
          <AiBasicsTabBar
            tab={tab}
            labels={{
              identity: tr('aiSetupBasicsIdentityHeading'),
              style: tr('aiSetupBasicsStyleTab'),
              greetings: tr('aiSetupGreetingsHeading'),
            }}
            onChange={setTab}
          />
          <ScrollView
            style={styles.flex}
            contentContainerStyle={styles.scroll}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
            {tab === 'identity' ? (
              <AiBasicsIdentityTab
                payload={basics}
                onChange={(next) => multi.setPayload('ai_basics', next)}
                tr={tr}
              />
            ) : null}
            {tab === 'style' ? (
              <AiBasicsStyleTab
                payload={style}
                onChange={(next) => multi.setPayload('style', next)}
                tr={tr}
              />
            ) : null}
            {tab === 'greetings' ? (
              <AiBasicsGreetingsList
                items={items}
                query={query}
                onQueryChange={setQuery}
                onAdd={handleAddGreeting}
                onSelect={openGreeting}
                onRequestDelete={(id) => confirmDelete(id)}
                tr={tr}
              />
            ) : null}
          </ScrollView>
          {tab !== 'greetings' ? (
            <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 12) }]}>
              <PrimaryButton
                label={tr('aiSetupSaveChanges')}
                onPress={() => void multi.save()}
                loading={multi.saving}
                disabled={!multi.dirty || !multi.canSave}
                style={styles.saveBtn}
              />
            </View>
          ) : null}
        </View>
      ) : null}

      {!multi.loading && editingGreeting && selected ? (
        <KeyboardAvoidingView
          style={styles.flex}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <ScrollView
            contentContainerStyle={styles.editScroll}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
          >
            <GreetingEditView
              item={selected}
              isNew={isNewGreeting}
              uploading={media.uploading}
              uploadError={media.uploadError}
              onTitle={(name) => patchGreeting(selected.id, { name })}
              onNote={(notes) => patchGreeting(selected.id, withGreetingNote(selected, notes))}
              onAddResource={(kind) => void media.addResource(kind)}
              onRemoveResource={(id) =>
                patchGreeting(selected.id, {
                  attachments: selected.attachments.filter((row) => row.id !== id),
                })
              }
              onReplaceResource={(att) => void media.addResource(att.kind, att.id)}
              onEditCaption={media.editResource}
              onMoveResource={(id, direction) =>
                patchGreeting(selected.id, {
                  attachments: moveById(selected.attachments, id, direction),
                })
              }
              tr={tr}
            />
          </ScrollView>
          <View style={[styles.editFooter, { paddingBottom: Math.max(insets.bottom, 12) }]}>
            {!isNewGreeting ? (
              <Pressable
                onPress={() => confirmDelete()}
                accessibilityRole="button"
                accessibilityLabel={tr('aiSetupDeleteGreeting')}
                style={({ pressed }) => [styles.deleteBtn, pressed && styles.pressed]}
              >
                <AppIcon icon={feather('trash-2')} size={18} color="#DC2626" />
                <Text style={styles.deleteText}>{tr('aiSetupDeleteGreeting')}</Text>
              </Pressable>
            ) : null}
            <PrimaryButton
              label={tr('aiSetupSaveGreeting')}
              onPress={() => void multi.save()}
              loading={multi.saving}
              disabled={!multi.dirty || !multi.canSave}
              style={styles.saveBtn}
            />
          </View>
        </KeyboardAvoidingView>
      ) : null}

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
        onChangeDescription={(description) =>
          media.setPrompt((row) => (row ? { ...row, description } : row))
        }
        onSave={media.commitPrompt}
        onClose={media.closePrompt}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  scroll: { paddingBottom: 16, flexGrow: 1 },
  editScroll: { paddingBottom: 16 },
  error: { color: '#DC2626', fontFamily: fonts.body, marginBottom: 8 },
  warn: { color: '#D97706', fontFamily: fonts.body, marginBottom: 8 },
  footer: { paddingTop: 8 },
  editFooter: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingTop: 8 },
  saveBtn: { flex: 1, backgroundColor: AB_FOREST, borderRadius: 12 },
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
  pressed: { opacity: 0.7 },
});
