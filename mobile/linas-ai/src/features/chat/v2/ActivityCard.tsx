import { StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../../theme';
import type { CmProposalReview } from '../../cm/cmProposalReview';
import type { StreamCard } from './useOwnerStream';
import { ProposalCard } from './ProposalCard';

type Props = {
  card: StreamCard;
  onApproveDraft?: (token: string, opts?: { delete_ids?: string[] }) => void;
  onDiscard?: (token?: string, proposalId?: string) => void;
  onEditProposal?: (proposalId: string, token?: string) => void;
  onOpenCm?: (review?: CmProposalReview) => void;
  onRetry?: () => void;
};

export function ActivityCard(props: Props) {
  const { card } = props;
  if (card.kind === 'proposal') {
    return <ProposalCard {...props} />;
  }
  return <GenericActivityCard card={card} />;
}

function GenericActivityCard({ card }: { card: StreamCard }) {
  const { colors } = useTheme();
  const kindLabel =
    card.kind === 'diagnosis'
      ? 'Diagnosis'
      : card.kind === 'setup'
        ? 'Setup'
        : card.kind === 'progress'
          ? 'Activity'
          : card.kind === 'success'
            ? 'Applied'
            : card.kind === 'failure'
              ? 'Failed'
              : card.kind;

  return (
    <View
      style={[styles.card, { backgroundColor: colors.bgElevated, borderColor: colors.border }]}
      accessibilityLabel={`${kindLabel} card: ${card.title}`}
    >
      <Text style={[styles.kind, { color: colors.textDim }]}>{kindLabel}</Text>
      <Text style={[styles.title, { color: colors.text }]}>{card.title}</Text>
      {card.body ? <Text style={[styles.body, { color: colors.textMuted }]}>{card.body}</Text> : null}
      {card.status ? (
        <Text style={[styles.status, { color: colors.accent }]}>{card.status.replace(/_/g, ' ')}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    padding: spacing.md,
    borderRadius: radii.md,
    borderWidth: 1,
  },
  kind: {
    fontFamily: fonts.bodyMedium,
    fontSize: 11,
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  body: { fontFamily: fonts.body, fontSize: 13, marginTop: 4 },
  status: { fontFamily: fonts.body, fontSize: 12, marginTop: 6, textTransform: 'capitalize' },
});
