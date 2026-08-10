import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import type { CmProposalReview } from '../cm/cmProposalReview';
import { ScreenChrome } from '../shared/ScreenChrome';
import { FaqCreateView } from './FaqCreateView';
import { FaqDetailView } from './FaqDetailView';
import { FaqListView } from './FaqListView';
import {
  archiveFaq,
  createFaq,
  listFaq,
  patchFaqVariant,
  regenerateFaq,
  type FaqEntitlement,
  type FaqGroup,
} from './faqApi';
import type { FaqLangId } from './faqLanguages';
import { variantForLang } from './faqPreview';

type Mode = 'list' | 'create' | 'detail';

type Props = {
  onBack: () => void;
  onAskLinas?: () => void;
  proposalReview?: CmProposalReview | null;
};

export function FaqScreen({ onBack, onAskLinas, proposalReview }: Props) {
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<FaqGroup[]>([]);
  const [entitlement, setEntitlement] = useState<FaqEntitlement | null>(null);
  const [quotaDisplay, setQuotaDisplay] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<Mode>('list');
  const [selected, setSelected] = useState<FaqGroup | null>(null);
  const [activeLang, setActiveLang] = useState<FaqLangId>('ar');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [language, setLanguage] = useState<FaqLangId>('ar');
  const [savedFlash, setSavedFlash] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listFaq({ q: query.trim() || undefined });
      setItems(data.items);
      setEntitlement(data.entitlement);
      setQuotaDisplay(data.quotaDisplay);
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
      await createFaq({ question: q, answer: a, language });
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

  async function handleArchive() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await archiveFaq(selected.qa_group_id);
      setSelected(null);
      setMode('list');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : tr('faqCreateError'));
    } finally {
      setSaving(false);
    }
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
    <ScreenChrome title={tr('faqTitle')} subtitle={tr('faqSub')} onBack={onBack}>
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
            quotaDisplay={quotaDisplay}
            query={query}
            onQueryChange={setQuery}
            onCreate={() => {
              setQuestion('');
              setAnswer('');
              setLanguage('ar');
              setMode('create');
            }}
            onAskLinas={() => onAskLinas?.()}
            onSelect={(group) => {
              setSelected(group);
              setActiveLang('ar');
              setMode('detail');
            }}
            onRefresh={() => void load()}
            tr={tr}
          />
        ) : null}
        {mode === 'create' ? (
          <FaqCreateView
            question={question}
            answer={answer}
            language={language}
            saving={saving}
            onQuestion={setQuestion}
            onAnswer={setAnswer}
            onLanguage={setLanguage}
            onSave={() => void handleCreate()}
            onCancel={() => setMode('list')}
            tr={tr}
          />
        ) : null}
        {mode === 'detail' && selected ? (
          <FaqDetailView
            group={selected}
            activeLang={activeLang}
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
