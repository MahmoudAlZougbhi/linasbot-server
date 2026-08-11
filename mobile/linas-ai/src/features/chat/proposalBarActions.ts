/** Proposal bar Approve / Cancel / Edit helpers — keep ChatScreen under the 400-line limit. */

export function rejectTokenFromApprove(token: string): string | null {
  const prefix = 'approve_cm_patch:';
  if (!token.startsWith(prefix)) return null;
  const id = token.slice(prefix.length).trim();
  return id ? `reject_cm_patch:${id}` : null;
}

export type ProposalApproveOpts = { delete_ids?: string[] };

export function buildApproveSendOpts(token: string, approveOpts?: ProposalApproveOpts) {
  return {
    confirm_tool: token,
    tool_args: approveOpts?.delete_ids?.length ? { delete_ids: approveOpts.delete_ids } : undefined,
    revise_proposal_id: null as string | null,
  };
}

export function buildDiscardSendOpts(token?: string) {
  const rejectToken = token ? rejectTokenFromApprove(token) : null;
  if (!rejectToken) return null;
  return {
    confirm_tool: rejectToken,
    revise_proposal_id: null as string | null,
  };
}
