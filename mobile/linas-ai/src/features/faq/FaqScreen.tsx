import { useEffect, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';

import { faqWriteErrorMessage } from './faqWriteError';
import { ScreenSkeleton } from '../../components/ScreenSkeleton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import type { CmProposalReview } from '../cm/cmProposalReview';
import { ScreenChrome } from '../shared/ScreenChrome';
import { FaqCreateView } from './FaqCreateView';
import { FaqDetailView } from './FaqDetailView';
import { FaqLanguagePickerModal } from './FaqLanguagePickerModal';
import { FaqListView } from './FaqListView';
import { FaqResourcesEditor } from './FaqResourcesEditor';
import {
  archiveFaq,
  createFaq,
  deleteSmartAnswerLanguage,
  patchFaqVariant,
  regenerateFaq,
  saveSmartAnswerLanguages,
  type FaqGroup,
} from './faqApi';
import type { FaqLangId } from './faqLanguages';
import { langNativeLabel } from './faqLanguages';
import { variantForLang } from './faqPreview';
import { useFaqList } from './useFaqList';

type Mode = 'list' | 'create' | 'detail';

type Props = {
  onAskLinas?: () => void;
  proposalReview?: CmProposalReview | null;
};

export function FaqScreen({ proposalReview }: Props) {
  const { tr } = useI18n();
  const list = useFaqList(tr);
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<Mode>('list');
  const [activeLang, setActiveLang] = useState<FaqLangId>('en');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [savedFlash, setSavedFlash] = useState(false);
  const [langPickerOpen, setLangPickerOpen] = useState(false);
  const [pendingLangSave, setPendingLangSave] = useState<string[] | null>(null);

  useEffect(() => {
    if (!list.selected) return;
    const variant = variantForLang(list.selected, activeLang);
    setQuestion(typeof variant?.question === 'string' ? variant.question : '');
    setAnswer(typeof variant?.answer === 'string' ? variant.answer : '');
  }, [list.selected, activeLang]);

  async function handleCreate() {
    const q = question.trim();
    const a = answer.trim();
    if (!q || !a) {
      list.setError(tr('likeFaqNeedBoth'));
      return;
    }
    setSaving(true);
    list.setError(null);
    try {
      await createFaq({ question: q, answer: a });
      setQuestion('');
      setAnswer('');
      setMode('list');
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2500);
      await list.reloadAfterWrite();
    } catch (err) {
      list.setError(faqWriteErrorMessage(err, tr));
    } finally {
      setSaving(false);
    }
  }

  async function commitLanguageSave(languages: string[], translateExisting: boolean) {
    setSaving(true);
    list.setError(null);
    try {
      await saveSmartAnswerLanguages({ languages, translateExisting });
      list.setSmartAnswerLanguages(languages);
      setLangPickerOpen(false);
      setPendingLangSave(null);
      await list.reloadAfterWrite();
    } catch (err) {
      list.setError(faqWriteErrorMessage(err, tr));
    } finally {
      setSaving(false);
    }
  }

  function handleLanguageSave(languages: string[]) {
    const added = languages.filter((lang) => !list.smartAnswerLanguages.includes(lang));
    if (added.length && list.items.length > 0) {
      setPendingLangSave(languages);
      Alert.alert(
        tr('faqTranslateExistingTitle'),
        tr('faqTranslateExistingBody').replace('{lang}', added.join(', ')),
        [
          { text: tr('faqTranslateSkip'), style: 'cancel', onPress: () => void commitLanguageSave(languages, false) },
          { text: tr('faqTranslateAll'), onPress: () => void commitLanguageSave(languages, true) },
        ],
      );
      return;
    }
    void commitLanguageSave(languages, false);
  }

  function handleRemoveLanguage(langId: string) {
    if (list.smartAnswerLanguages.length <= 1) return;
    const langName = langNativeLabel(langId);
    Alert.alert(tr('faqRemoveLangTitle'), tr('faqRemoveLangBody').replace('{lang}', langName), [
      { text: tr('usersCancel'), style: 'cancel' },
      {
        text: tr('faqRemoveLangConfirm'),
        style: 'destructive',
        onPress: () => {
          setSaving(true);
          list.setError(null);
          void deleteSmartAnswerLanguage(langId)
            .then(() => {
              list.setSmartAnswerLanguages((prev) => prev.filter((id) => id !== langId));
              return list.reloadAfterWrite();
            })
            .catch((err) => {
              list.setError(faqWriteErrorMessage(err, tr));
            })
            .finally(() => setSaving(false));
        },
      },
    ]);
  }

  async function handleSaveVariant() {
    if (!list.selected) return;
    setSaving(true);
    list.setError(null);
    try {
      await patchFaqVariant(list.selected.qa_group_id, activeLang, {
        question: question.trim(),
        answer: answer.trim(),
      });
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
      await list.reloadAfterWrite();
    } catch (err) {
      list.setError(faqWriteErrorMessage(err, tr));
    } finally {
      setSaving(false);
    }
  }

  async function handleRegenerate() {
    if (!list.selected) return;
    setSaving(true);
    list.setError(null);
    try {
      await regenerateFaq(list.selected.qa_group_id);
      await list.reloadAfterWrite();
    } catch (err) {
      list.setError(faqWriteErrorMessage(err, tr));
    } finally {
      setSaving(false);
    }
  }

  async function handleArchiveId(qaGroupId: string) {
    setSaving(true);
    list.setError(null);
    try {
      await archiveFaq(qaGroupId);
      list.setSelected((prev) => (prev?.qa_group_id === qaGroupId ? null : prev));
      setMode('list');
      await list.reloadAfterWrite();
    } catch (err) {
      list.setError(faqWriteErrorMessage(err, tr));
    } finally {
      setSaving(false);
    }
  }

  function confirmDelete(group: FaqGroup) {
    Alert.alert(tr('faqDeleteTitle'), tr('faqDeleteBody'), [
      { text: tr('usersCancel'), style: 'cancel' },
      {
        text: tr('faqDeleteConfirm'),
        style: 'destructive',
        onPress: () => void handleArchiveId(group.qa_group_id),
      },
    ]);
  }

  const proposalItem = proposalReview?.proposedItem;
  const proposalVariants = Array.isArray(proposalItem?.variants) ? proposalItem?.variants : [];
  const proposalBits = proposalVariants
    .filter((v): v is Record<string, unknown> => Boolean(v) && typeof v === 'object')
    .map((v) => {
      const lang = String(v.language || '');
      const q = String(v.question || '').trim();
      const a = String(v.answer || '').trim();
      return q || a ? `[${lang}] Q: ${q}\nA: ${a}` : '';
    })
    .filter(Boolean)
    .join('\n\n');

  return (
    <ScreenChrome
      title={tr('faqTitle')}
      subtitle={mode === 'list' ? tr('faqSub') : undefined}
      compactTitle
    >
      {list.loading && !list.hasLoadedOnce ? <ScreenSkeleton variant="list" /> : null}
      {list.hasLoadedOnce && list.error ? <Text style={styles.error}>{list.error}</Text> : null}
      {list.hasLoadedOnce && savedFlash ? <Text style={styles.ok}>{tr('faqSaved')}</Text> : null}
      {list.hasLoadedOnce && proposalBits ? (
        <View style={[styles.card, { borderColor: colors.accent, marginBottom: spacing.sm }]}>
          <Text style={styles.section}>AI proposal preview — not saved</Text>
          <Text style={styles.hint}>{proposalBits}</Text>
        </View>
      ) : null}

      {list.hasLoadedOnce ? (
      <ScrollView contentContainerStyle={styles.list}>
        {mode === 'list' ? (
          <FaqListView
            items={list.items}
            entitlement={list.entitlement}
            smartAnswerLanguages={list.smartAnswerLanguages}
            query={list.query}
            onQueryChange={list.setQuery}
            onCreate={() => {
              setQuestion('');
              setAnswer('');
              setMode('create');
            }}
            onSelect={(group) => {
              list.setSelected(group);
              setActiveLang(
                (list.smartAnswerLanguages.includes('en') ? 'en' : list.smartAnswerLanguages[0]) || 'en',
              );
              setMode('detail');
            }}
            onDelete={confirmDelete}
            onAddLanguage={() => setLangPickerOpen(true)}
            onRemoveLanguage={handleRemoveLanguage}
            tr={tr}
          />
        ) : null}
        {mode === 'create' ? (
          <FaqCreateView
            question={question}
            answer={answer}
            saving={saving}
            onQuestion={setQuestion}
            onAnswer={setAnswer}
            onSave={() => void handleCreate()}
            onCancel={() => setMode('list')}
            tr={tr}
          />
        ) : null}
        {mode === 'detail' && list.selected ? (
          <FaqDetailView
            group={list.selected}
            activeLang={activeLang}
            smartAnswerLanguages={list.smartAnswerLanguages}
            question={question}
            answer={answer}
            saving={saving}
            onLang={setActiveLang}
            onQuestion={setQuestion}
            onAnswer={setAnswer}
            onSaveVariant={() => void handleSaveVariant()}
            onRegenerate={() => void handleRegenerate()}
            onArchive={() => void handleArchiveId(list.selected!.qa_group_id)}
            onBack={() => {
              list.setSelected(null);
              setMode('list');
            }}
            tr={tr}
          >
            <FaqResourcesEditor
              group={list.selected}
              onUpdated={(next) => list.setSelected(next)}
              tr={tr}
            />
          </FaqDetailView>
        ) : null}
      </ScrollView>
      ) : null}

      <FaqLanguagePickerModal
        visible={langPickerOpen}
        selected={pendingLangSave || list.smartAnswerLanguages}
        catalog={list.languageCatalog}
        saving={saving}
        onClose={() => {
          setLangPickerOpen(false);
          setPendingLangSave(null);
        }}
        onSave={handleLanguageSave}
        tr={tr}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 24 },
  section: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  hint: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  error: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
  ok: { color: colors.success, fontFamily: fonts.body, marginBottom: spacing.sm },
});
