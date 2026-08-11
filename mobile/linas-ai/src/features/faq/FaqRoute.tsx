import { queueSetupHandoff } from '../chat/pendingSetupHandoff';
import type { CmProposalReview } from '../cm/cmProposalReview';
import { FaqScreen } from './FaqScreen';
import { FAQ_ASK_LINAS_PROMPT } from './faqLanguages';

type Props = {
  proposalReview?: CmProposalReview | null;
  onGoChat: () => void;
};

/** FAQ route shell — Ask Linas handoff stays out of App.tsx line budget. */
export function FaqRoute({ proposalReview, onGoChat }: Props) {
  return (
    <FaqScreen
      proposalReview={proposalReview ?? null}
      onAskLinas={() => {
        queueSetupHandoff({ text: FAQ_ASK_LINAS_PROMPT, mode: 'work', autoSend: true });
        onGoChat();
      }}
    />
  );
}
