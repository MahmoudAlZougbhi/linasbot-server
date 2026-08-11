import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { CmProposalReview } from '../../cm/cmProposalReview';
import type { StreamCard } from './useOwnerStream';

type Props = {
  card: StreamCard;
  onApproveDraft?: (token: string, opts?: { delete_ids?: string[] }) => void;
  onDiscard?: (token?: string, proposalId?: string) => void;
  onEditProposal?: (proposalId: string) => void;
  onOpenCm?: (review?: CmProposalReview) => void;
  onRetry?: () => void;
  onRefresh?: () => void;
};

function str(v: unknown): string {
  if (typeof v === 'string') return v;
  if (v == null) return '';
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

type DeleteTarget = { id: string; title: string };

/** Unified CM proposal / delete bar — Approve | Cancel | Edit (+ per-item X). */
export function ProposalCard({
  card,
  onApproveDraft,
  onDiscard,
  onEditProposal,
  onOpenCm,
  onRetry,
  onRefresh,
}: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const data = (card.data || {}) as Record<string, unknown>;
  const preview = (data.preview && typeof data.preview === 'object'
    ? (data.preview as Record<string, unknown>)
    : {}) as Record<string, unknown>;
  const token = str(data.confirmation_token);
  const proposalId = str(data.proposal_id);
  const status = str(card.status || 'draft_proposal');
  const section = str(preview.section || preview.cm_section || data.section);
  const field = str(preview.field || preview.cm_field || data.field);
  const isDelete = str(preview.kind) === 'cm_delete' || str(preview.action) === 'delete';
  const targets = useMemo(() => {
    const raw = preview.targets;
    if (!Array.isArray(raw)) return [] as DeleteTarget[];
    return raw
      .filter((row): row is Record<string, unknown> => !!row && typeof row === 'object')
      .map((row) => ({
        id: str(row.id),
        title: str(row.title || row.id) || 'item',
      }))
      .filter((t) => t.id);
  }, [preview.targets]);
  const [keptIds, setKeptIds] = useState<string[]>(() => targets.map((t) => t.id));
  useEffect(() => {
    setKeptIds(targets.map((t) => t.id));
  }, [targets]);

  const currentValue = str(
    preview.current_value ?? preview.before ?? preview.current_sample ?? data.current_value,
  );
  const proposedValue = str(
    preview.proposed_value ??
      preview.after ??
      preview.proposed_sample ??
      preview.proposed_text ??
      preview.text ??
      card.body,
  );
  const reviewTarget: CmProposalReview | undefined = section
    ? {
        section,
        proposalId: proposalId || undefined,
        patch:
          preview.patch && typeof preview.patch === 'object' && !Array.isArray(preview.patch)
            ? (preview.patch as Record<string, unknown>)
            : undefined,
        proposedItem:
          preview.proposed_item &&
          typeof preview.proposed_item === 'object' &&
          !Array.isArray(preview.proposed_item)
            ? (preview.proposed_item as Record<string, unknown>)
            : undefined,
        articleId: str(preview.article_id) || undefined,
        qaGroupId: str(preview.qa_group_id) || undefined,
      }
    : undefined;
  const reason = str(preview.reason || data.reason);
  const impact = str(preview.impact || data.impact);
  const visibleTargets = targets.filter((t) => keptIds.includes(t.id));
  const canApprove = Boolean(token) && (!isDelete || visibleTargets.length > 0);

  return (
    <View
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
      accessibilityLabel={`Proposal ${card.title}. Status ${status}.`}
    >
      <View style={styles.head}>
        <Text style={[styles.title, { color: colors.text }]}>{card.title}</Text>
        <View style={styles.badges}>
          <Badge label={status.replace(/_/g, ' ')} tone="muted" />
          {isDelete ? <Badge label={tr('proposalDeleteBadge')} tone="danger" /> : null}
          <Badge label={tr('proposalDraftBadge')} tone="accent" />
        </View>
      </View>

      {proposalId ? (
        <Text style={[styles.meta, { color: colors.textDim }]}>ID {proposalId}</Text>
      ) : null}
      {section || field ? (
        <Text style={[styles.meta, { color: colors.textMuted }]}>
          {[section, field].filter(Boolean).join(' · ')}
        </Text>
      ) : null}

      {isDelete && visibleTargets.length ? (
        <View style={styles.targetList}>
          <Text style={[styles.label, { color: colors.textDim }]}>{tr('proposalWillDelete')}</Text>
          {visibleTargets.map((t) => (
            <View
              key={t.id}
              style={[styles.targetRow, { backgroundColor: colors.input, borderColor: colors.border }]}
            >
              <Text style={[styles.targetTitle, { color: colors.text }]} numberOfLines={2}>
                {t.title}
              </Text>
              <Pressable
                onPress={() => setKeptIds((prev) => prev.filter((id) => id !== t.id))}
                accessibilityLabel={tr('proposalRemoveFromSet')}
                hitSlop={8}
                style={styles.xHit}
              >
                <Text style={{ color: colors.danger, fontSize: 16, fontWeight: '700' }}>×</Text>
              </Pressable>
            </View>
          ))}
        </View>
      ) : null}

      {!isDelete && (currentValue || proposedValue) ? (
        <View style={styles.diff}>
          {currentValue ? (
            <>
              <Text style={[styles.label, { color: colors.textDim }]}>{tr('proposalCurrent')}</Text>
              <Text style={{ color: colors.textMuted }}>{currentValue}</Text>
            </>
          ) : null}
          <Text style={[styles.label, { color: colors.textDim, marginTop: 8 }]}>
            {tr('proposalProposed')}
          </Text>
          <View style={[styles.proposedBox, { backgroundColor: colors.input }]}>
            <Text style={{ color: colors.text }}>{proposedValue || '—'}</Text>
          </View>
        </View>
      ) : null}

      {reason ? (
        <Text style={[styles.meta, { color: colors.textMuted }]}>
          {tr('proposalReason')}: {reason}
        </Text>
      ) : null}
      {impact ? (
        <Text style={[styles.meta, { color: colors.textMuted }]}>
          {tr('proposalImpact')}: {impact}
        </Text>
      ) : null}

      <Text style={[styles.notApplied, { color: colors.textDim }]}>{tr('proposalNotAppliedYet')}</Text>

      <View style={styles.actions}>
        {canApprove ? (
          <Pressable
            style={[styles.primary, { backgroundColor: colors.accent }]}
            onPress={() =>
              onApproveDraft?.(
                token,
                isDelete ? { delete_ids: visibleTargets.map((t) => t.id) } : undefined,
              )
            }
            accessibilityLabel={tr('proposalApprove')}
          >
            <Text style={{ color: colors.onAccent, fontFamily: fonts.bodyMedium }}>
              {tr('proposalApprove')}
            </Text>
          </Pressable>
        ) : null}
        <View style={styles.rowActions}>
          <Pressable
            style={[styles.secondary, { borderColor: colors.border, flex: 1 }]}
            onPress={() => onDiscard?.(token, proposalId)}
            accessibilityLabel={tr('proposalCancel')}
          >
            <Text style={{ color: colors.text, fontFamily: fonts.bodyMedium }}>
              {tr('proposalCancel')}
            </Text>
          </Pressable>
          {proposalId ? (
            <Pressable
              style={[styles.secondary, { borderColor: colors.accent, flex: 1 }]}
              onPress={() => onEditProposal?.(proposalId)}
              accessibilityLabel={tr('proposalEdit')}
            >
              <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>
                {tr('proposalEdit')}
              </Text>
            </Pressable>
          ) : null}
        </View>
        <Pressable
          style={[styles.secondary, { borderColor: colors.border }]}
          onPress={() => onOpenCm?.(reviewTarget)}
          accessibilityLabel={tr('proposalReviewInSetup')}
        >
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>
            {tr('proposalReviewInSetup')}
          </Text>
        </Pressable>
        <View style={styles.rowActions}>
          {onRefresh ? (
            <Pressable onPress={onRefresh} accessibilityLabel={tr('proposalRefresh')}>
              <Text style={{ color: colors.textMuted }}>{tr('proposalRefresh')}</Text>
            </Pressable>
          ) : null}
          {onRetry ? (
            <Pressable onPress={onRetry} accessibilityLabel={tr('proposalRetry')}>
              <Text style={{ color: colors.textMuted }}>{tr('proposalRetry')}</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
    </View>
  );
}

function Badge({ label, tone }: { label: string; tone: 'accent' | 'muted' | 'danger' }) {
  const { colors } = useTheme();
  const bg = tone === 'accent' ? colors.accentSoft : colors.surfaceAlt;
  const fg = tone === 'accent' ? colors.accentDeep : tone === 'danger' ? colors.danger : colors.textMuted;
  return (
    <View style={[styles.badge, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontSize: 11, textTransform: 'capitalize' }}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    padding: spacing.md,
    borderRadius: radii.lg,
    borderWidth: 1,
    gap: 6,
  },
  head: { gap: 8 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  badges: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  badge: { borderRadius: radii.pill, paddingHorizontal: 8, paddingVertical: 4 },
  meta: { fontFamily: fonts.body, fontSize: 12 },
  label: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  targetList: { gap: 6, marginTop: 4 },
  targetRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 8,
  },
  targetTitle: { flex: 1, fontFamily: fonts.body, fontSize: 14 },
  xHit: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  diff: { marginTop: 4 },
  proposedBox: { borderRadius: radii.md, padding: spacing.md },
  notApplied: { fontFamily: fonts.body, fontSize: 12, marginTop: 4 },
  actions: { gap: 8, marginTop: 8 },
  primary: {
    minHeight: 48,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  secondary: {
    minHeight: 44,
    borderRadius: radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  rowActions: { flexDirection: 'row', gap: 8, alignItems: 'center' },
});
