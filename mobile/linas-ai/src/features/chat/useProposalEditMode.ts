import { useCallback, useState } from 'react';

import { resolveOwnerModeForOutgoing, type OwnerChatMode } from './ownerChatMode';

type SendFn = (
  text: string,
  opts?: {
    choice_id?: string;
    choice_set_id?: string;
    attachment_ids?: string[];
    confirm_tool?: string | null;
    tool_args?: Record<string, unknown>;
    revise_proposal_id?: string | null;
    owner_mode?: OwnerChatMode;
    reply_language?: 'en' | 'ar' | 'fr';
  },
) => Promise<'done' | 'error' | 'network_error' | 'cancelled' | 'skipped'>;

/** Owns composer Edit-chip state + revise_proposal_id for pending proposal bars. */
export function useProposalEditMode(
  ownerMode: OwnerChatMode,
  setOwnerMode: (mode: OwnerChatMode) => void,
  send: SendFn,
) {
  const [reviseProposalId, setReviseProposalId] = useState<string | null>(null);

  const ownerSendWithMode = useCallback(
    (text: string, opts?: Parameters<SendFn>[1]) => {
      const base = opts?.owner_mode ?? ownerMode;
      const mode = resolveOwnerModeForOutgoing(base, text);
      if (mode === 'work' && ownerMode !== 'work') setOwnerMode('work');
      const revise =
        opts?.revise_proposal_id !== undefined ? opts.revise_proposal_id : reviseProposalId;
      return send(text, {
        ...opts,
        owner_mode: mode,
        revise_proposal_id: revise,
      }).then((result) => {
        if (revise && result === 'done') setReviseProposalId(null);
        return result;
      });
    },
    [ownerMode, reviseProposalId, send, setOwnerMode],
  );

  return { reviseProposalId, setReviseProposalId, ownerSendWithMode };
}
