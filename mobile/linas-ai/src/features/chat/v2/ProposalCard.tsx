import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { CmProposalReview } from '../../cm/cmProposalReview';
import type { StreamCard } from './useOwnerStream';

type Props = {
  card: StreamCard;
  onApproveDraft?: (token: string) => void;
  onDiscard?: () => void;
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

/** Complete V2 Change Proposal card — PDF style + full backend fields/actions. */
export function ProposalCard({
  card,
  onApproveDraft,
  onDiscard,
  onOpenCm,
  onRetry,
  onRefresh,
}: Props) {
  const { colors } = useTheme();
  const data = (card.data || {}) as Record<string, unknown>;
  const preview = (data.preview && typeof data.preview === 'object'
    ? (data.preview as Record<string, unknown>)
    : {}) as Record<string, unknown>;
  const token = str(data.confirmation_token);
  const proposalId = str(data.proposal_id);
  const status = str(card.status || 'draft_proposal');
  const section = str(preview.section || preview.cm_section || data.section);
  const field = str(preview.field || preview.cm_field || data.field);
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
  const channels = Array.isArray(preview.channels)
    ? (preview.channels as unknown[]).map(str).filter(Boolean)
    : Array.isArray(data.channels)
      ? (data.channels as unknown[]).map(str).filter(Boolean)
      : [];
  const target = str(preview.target || data.target || 'Draft');
  const validation = str(preview.validation || data.validation);
  const conflict = str(preview.conflict || data.conflict);

  return (
    <View
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
      accessibilityLabel={`Proposal ${card.title}. Status ${status}.`}
    >
      <View style={styles.head}>
        <Text style={[styles.title, { color: colors.text }]}>{card.title}</Text>
        <View style={styles.badges}>
          <Badge label={status.replace(/_/g, ' ')} tone="muted" />
          <Badge label={target === 'Live' || target === 'Published' ? 'Live target' : 'Draft'} tone="accent" />
          {channels.length ? <Badge label={`${channels.length} channels`} tone="accent" /> : null}
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

      {channels.length ? (
        <View style={styles.chips}>
          <Text style={[styles.label, { color: colors.textDim }]}>WILL APPLY TO</Text>
          <View style={styles.chipRow}>
            {channels.map((c) => (
              <View key={c} style={[styles.chip, { backgroundColor: colors.surfaceAlt }]}>
                <Text style={{ color: colors.text, fontSize: 12 }}>{c}</Text>
              </View>
            ))}
          </View>
        </View>
      ) : null}

      {(currentValue || proposedValue) && (
        <View style={styles.diff}>
          {currentValue ? (
            <>
              <Text style={[styles.label, { color: colors.textDim }]}>CURRENT</Text>
              <Text style={{ color: colors.textMuted }}>{currentValue}</Text>
            </>
          ) : null}
          <Text style={[styles.label, { color: colors.textDim, marginTop: 8 }]}>PROPOSED</Text>
          <View style={[styles.proposedBox, { backgroundColor: colors.input }]}>
            <Text style={{ color: colors.text }}>{proposedValue || '—'}</Text>
          </View>
        </View>
      )}

      {reason ? <Text style={[styles.meta, { color: colors.textMuted }]}>Reason: {reason}</Text> : null}
      {impact ? <Text style={[styles.meta, { color: colors.textMuted }]}>Impact: {impact}</Text> : null}
      {validation ? (
        <Text style={[styles.meta, { color: colors.textMuted }]}>Validation: {validation}</Text>
      ) : null}
      {conflict ? (
        <Text style={[styles.meta, { color: colors.warning }]}>Conflict: {conflict}</Text>
      ) : null}

      <Text style={[styles.notApplied, { color: colors.textDim }]}>
        Not applied yet — approval saves Draft only. Publish stays separate.
      </Text>

      <View style={styles.actions}>
        {token ? (
          <Pressable
            style={[styles.primary, { backgroundColor: colors.accent }]}
            onPress={() => onApproveDraft?.(token)}
            accessibilityLabel="Approve and apply to Draft"
          >
            <Text style={{ color: colors.onAccent, fontFamily: fonts.bodyMedium }}>
              Approve and apply to Draft
            </Text>
          </Pressable>
        ) : null}
        <Pressable
          style={[styles.secondary, { borderColor: colors.border }]}
          onPress={() => onOpenCm?.(reviewTarget)}
          accessibilityLabel="Review in Content Management"
        >
          <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>
            Review in Content Management
          </Text>
        </Pressable>
        <View style={styles.rowActions}>
          {onRefresh ? (
            <Pressable onPress={onRefresh} accessibilityLabel="Refresh proposal">
              <Text style={{ color: colors.textMuted }}>Refresh</Text>
            </Pressable>
          ) : null}
          {onRetry ? (
            <Pressable onPress={onRetry} accessibilityLabel="Retry">
              <Text style={{ color: colors.textMuted }}>Retry</Text>
            </Pressable>
          ) : null}
          <Pressable onPress={onDiscard} accessibilityLabel="Discard proposal">
            <Text style={{ color: colors.danger }}>Discard</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

function Badge({ label, tone }: { label: string; tone: 'accent' | 'muted' }) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.badge,
        {
          backgroundColor: tone === 'accent' ? colors.accentSoft : colors.surfaceAlt,
        },
      ]}
    >
      <Text
        style={{
          color: tone === 'accent' ? colors.accentDeep : colors.textMuted,
          fontSize: 11,
          textTransform: 'capitalize',
        }}
      >
        {label}
      </Text>
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
  chips: { marginTop: 4 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { borderRadius: radii.pill, paddingHorizontal: 10, paddingVertical: 4 },
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
    minHeight: 48,
    borderRadius: radii.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  rowActions: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 4 },
});
