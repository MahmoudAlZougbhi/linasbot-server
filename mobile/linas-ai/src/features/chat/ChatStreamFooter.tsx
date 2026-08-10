import { Text, View } from 'react-native';

import type { CmProposalReview } from '../cm/cmProposalReview';
import { ChatBubble } from './ChatBubble';
import { chatScreenStyles as styles } from './chatScreenStyles';
import { ThinkingRow } from './ThinkingRow';
import type { ProposedPatch } from './useChatSession';
import { ActivityCard } from './v2/ActivityCard';
import type { StreamCard } from './v2/useOwnerStream';

type Props = {
  thinking: boolean;
  thinkingLabel: string;
  statusRows: { id: string; text: string }[];
  liveText: string;
  cards: StreamCard[];
  proposedPatch: ProposedPatch | null;
  proposedCmPatchLabel: string;
  onApproveDraft: (token: string) => void;
  onDiscardProposal: () => void;
  onOpenCm: (review?: CmProposalReview) => void;
  onRetryLast: () => void;
};

export function ChatStreamFooter({
  thinking,
  thinkingLabel,
  statusRows,
  liveText,
  cards,
  proposedPatch,
  proposedCmPatchLabel,
  onApproveDraft,
  onDiscardProposal,
  onOpenCm,
  onRetryLast,
}: Props) {
  // Same live turn slot: Thinking… until first delta, then one accumulating bubble.
  const showThinking = thinking && !liveText;

  return (
    <View>
      {statusRows.map((s) => (
        <Text key={s.id} style={styles.gate} accessibilityLiveRegion="polite">
          {s.text}
        </Text>
      ))}
      {showThinking ? <ThinkingRow label={thinkingLabel} /> : null}
      {liveText ? (
        <ChatBubble
          message={{
            id: 'live-stream',
            role: 'assistant',
            content: liveText,
            created_at: Date.now() / 1000,
          }}
          showActions={false}
        />
      ) : null}
      {cards.map((c) => (
        <ActivityCard
          key={c.id}
          card={c}
          onApproveDraft={onApproveDraft}
          onDiscard={onDiscardProposal}
          onOpenCm={onOpenCm}
          onRetry={onRetryLast}
        />
      ))}
      {proposedPatch?.confirmation_token && !cards.some((c) => c.kind === 'proposal') ? (
        <ActivityCard
          card={{
            id: 'legacy-proposal',
            kind: 'proposal',
            title: proposedCmPatchLabel,
            body: '',
            status: 'pending_approval',
            data: proposedPatch as unknown as Record<string, unknown>,
          }}
          onApproveDraft={onApproveDraft}
          onDiscard={onDiscardProposal}
          onOpenCm={onOpenCm}
        />
      ) : null}
    </View>
  );
}
