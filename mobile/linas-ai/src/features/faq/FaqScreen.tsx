import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import type { CmProposalReview } from '../cm/cmProposalReview';
import { ScreenChrome } from '../shared/ScreenChrome';
import { FaqCreateView } from './FaqCreateView';
import { FaqDetailView } from './FaqDetailView';
import { FaqLanguagePickerModal } from './FaqLanguagePickerModal';
import { FaqListView } from './FaqListView';
import {
  archiveFaq,
  createFaq,
  listFaq,
  patchFaqVariant,
  regenerateFaq,
  saveSmartAnswerLanguages,
  type FaqEntitlement,
  type FaqGroup,
} from './faqApi';
import type { FaqLangId, SmartAnswerLang } from './faqLanguages';
import { setSmartAnswerLanguageCatalog } from './faqLanguages';
import { variantForLang } from './faqPreview';

type Mode = 'list' | 'create' | 'detail';

type Props = {
  onAskLinas?: () => void;
  proposalReview?: CmProposalReview | null;
};

export function FaqScreen({ proposalReview }: Props) {
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<FaqGroup[]>([]);
  const [entitlement, setEntitlement] = useState<FaqEntitlement | null>(null);
  const [smartAnswerLanguages, setSmartAnswerLanguages] = useState<string[]>(['ar', 'en', 'fr', 'franco']);
  const [languageCatalog, setLanguageCatalog] = useState<SmartAnswerLang[]>([]);
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<Mode>('list');
  const [selected, setSelected] = useState<FaqGroup | null>(null);
  const [activeLang, setActiveLang] = useState<FaqLangId>('ar');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [savedFlash, setSavedFlash] = useState(false);
  const [langPickerOpen, setLangPickerOpen] = useState(false);
  const [pendingLangSave, setPendingLangSave] = useState<string[] | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listFaq({ q: query.trim() || undefined });
      setItems(data.items);
      setEntitlement(data.entitlement);
      if (data.smartAnswerLanguages.length) {
        setSmartAnswerLanguages(data.smartAnswerLanguages);
      }
      if (data.catalog.length) {
        setLanguageCatalog(data.catalog);
        setSmartAnswerLanguageCatalog(data.catalog);
      }
      setSelected((prev) => {
        if (!prev) return null;
        return data.items.find((g) => g.qa_group_id === prev.qa_group_id) || null;
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr('faqLoadError'));
    } finally {
      setLoading(false);
    }
  }, [query, tr]);

  useEffect(() => {
    const handle = setTimeout(() => {
      void load();
    }, query ? 280 : 0);
    return () => clearTimeout(handle);
  }, [load, query]);

  useEffect(() => {
    if (!selected) return;
    const variant = variantForLang(selected, activeLang);
    setQuestion(typeof variant?.question === 'string' ? variant.question : '');
    setAnswer(typeof variant?.answer === 'string' ? variant.answer : '');
  }, [selected, activeLang]);

  async function handleCreate() {
    const q = question.trim();
    const a = answer.trim();
    if (!q || !a) {
      setError(tr('likeFaqNeedBoth'));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createFaq({ question: q, answer: a });
      setQuestion('');
      setAnswer('');
      setMode('list');
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2500);
      await load();
    } catch (err) {
      if (err instanceof ApiError && (err.status === 402 || err.status === 403)) {
        setError(tr('faqQuotaUpgrade'));
      } else {
        setError(err instanceof ApiError ? err.message : tr('faqCreateError'));
      }
    } finally {
      setSaving(false);
    }
  }

  async function commitLanguageSave(languages: string[], translateExisting: boolean) {
    setSaving(true);
    setError(null);
    try {
      await saveSmartAnswerLanguages({ languages, translateExisting });
      setLangPickerOpen(false);
      setPendingLangSave(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr('faqCreateError'));
    } finally {
      setSaving(false);
    }
  }

  function handleLanguageSave(languages: string[]) {
    const added = languages.filter((lang) => !smartAnswerLanguages.includes(lang));
    if (added.length && items.length > 0) {
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
    const next = smartAnswerLanguages.filter((x) => x !== langId);
    if (next.length === 0) return;
    void commitLanguageSave(next, false);
  }

  async function handleSaveVariant() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await patchFaqVariant(selected.qa_group_id, activeLang, {
        question: question.trim(),
        answer: answer.trim(),
      });
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr('faqCreateError'));
    } finally {
      setSaving(false);
    }
  }

  async function handleRegenerate() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await regenerateFaq(selected.qa_group_id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr('faqCreateError'));
    } finally {
      setSaving(false);
    }
  }

  async function handleArchiveId(qaGroupId: string) {
    setSaving(true);
    setError(null);
    try {
      await archiveFaq(qaGroupId);
      setSelected((prev) => (prev?.qa_group_id === qaGroupId ? null : prev));
      setMode('list');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr('faqCreateError'));
    } finally {
      setSaving(false);
    }
  }

  function handleArchive() {
    if (!selected) return;
    void handleArchiveId(selected.qa_group_id);
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
    <ScreenChrome title={tr('faqTitle')}>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {savedFlash ? <Text style={styles.ok}>{tr('faqSaved')}</Text> : null}
      {proposalBits ? (
        <View style={[styles.card, { borderColor: colors.accent, marginBottom: spacing.sm }]}>
          <Text style={styles.section}>AI proposal preview — not saved</Text>
          <Text style={styles.hint}>{proposalBits}</Text>
        </View>
      ) : null}

      <ScrollView contentContainerStyle={styles.list}>
        {mode === 'list' ? (
          <FaqListView
            items={items}
            entitlement={entitlement}
            smartAnswerLanguages={smartAnswerLanguages}
            query={query}
            onQueryChange={setQuery}
            onCreate={() => {
              setQuestion('');
              setAnswer('');
              setMode('create');
            }}
            onSelect={(group) => {
              setSelected(group);
              setActiveLang(
                (smartAnswerLanguages.includes('en') ? 'en' : smartAnswerLanguages[0]) || 'en',
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
        {mode === 'detail' && selected ? (
          <FaqDetailView
            group={selected}
            activeLang={activeLang}
            smartAnswerLanguages={smartAnswerLanguages}
            question={question}
            answer={answer}
            saving={saving}
            onLang={setActiveLang}
            onQuestion={setQuestion}
            onAnswer={setAnswer}
            onSaveVariant={() => void handleSaveVariant()}
            onRegenerate={() => void handleRegenerate()}
            onArchive={() => void handleArchive()}
            onBack={() => {
              setSelected(null);
              setMode('list');
            }}
            tr={tr}
          />
        ) : null}
      </ScrollView>

      <FaqLanguagePickerModal
        visible={langPickerOpen}
        selected={pendingLangSave || smartAnswerLanguages}
        catalog={languageCatalog}
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
