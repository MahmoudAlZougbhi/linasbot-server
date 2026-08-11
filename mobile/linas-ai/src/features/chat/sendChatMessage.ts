import { isNetworkFailure } from '../../api/networkError';
import type { PendingFile } from './v2/pickAttachment';
import { isImageMime } from './v2/pickAttachment';
import { uploadOwnerAttachment } from './v2/useOwnerStream';
import type { VoiceState } from './useVoiceDraft';

type GuestSend = (
  content: string,
) => Promise<'done' | 'gated' | 'rejected' | 'error' | 'network_error' | 'skipped'>;

type OwnerTurnSend = (
  text: string,
  opts?: {
    attachment_ids?: string[];
    choice_id?: string;
    choice_set_id?: string;
    confirm_tool?: string | null;
    owner_mode?: 'chat' | 'work';
  },
) => Promise<'done' | 'error' | 'network_error' | 'cancelled' | 'skipped'>;

type Args = {
  isAuthenticated: boolean;
  draft: string;
  setDraft: (v: string) => void;
  pendingFiles: PendingFile[];
  setPendingFiles: (files: PendingFile[] | ((prev: PendingFile[]) => PendingFile[])) => void;
  voiceState: VoiceState;
  conversationId: string | null;
  guestGated: boolean;
  guestSend: GuestSend;
  ownerSend: OwnerTurnSend;
  appendOptimisticUser: (content: string, localImageUris?: string[]) => string;
  removeOptimisticUser: (id: string) => void;
  autoTitleFromOutgoing: (content: string) => void;
  openAuthPreservingDraft: (hard?: boolean) => void;
  setOffline: (v: boolean) => void;
  setSendError: (v: string | null) => void;
  scrollToBottom: () => void;
  imagePreviewByContent: { current: Record<string, string[]> };
};

function restoreDraft(
  setDraft: (v: string) => void,
  text: string,
  setPendingFiles: Args['setPendingFiles'],
  files: PendingFile[],
) {
  setDraft(text);
  setPendingFiles(files);
}

export async function sendChatMessage(args: Args): Promise<void> {
  const {
    isAuthenticated,
    draft,
    setDraft,
    pendingFiles,
    setPendingFiles,
    voiceState,
    conversationId,
    guestGated,
    guestSend,
    ownerSend,
    appendOptimisticUser,
    removeOptimisticUser,
    autoTitleFromOutgoing,
    openAuthPreservingDraft,
    setOffline,
    setSendError,
    scrollToBottom,
    imagePreviewByContent,
  } = args;

  if (!isAuthenticated) {
    if (guestGated) {
      openAuthPreservingDraft(true);
      return;
    }
    if (pendingFiles.length > 0) {
      setSendError('guestMediaBlocked');
      return;
    }
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    scrollToBottom();
    const result = await guestSend(text);
    if (result === 'skipped' || result === 'rejected' || result === 'error' || result === 'network_error') {
      setDraft(text);
      if (result === 'network_error') {
        setSendError(null);
        setOffline(true);
      } else if (result === 'error') {
        setOffline(false);
        // Guest session already set a typed error (word limit / model / messageFailed).
      } else {
        setOffline(false);
      }
      return;
    }
    setOffline(false);
    setSendError(null);
    return;
  }

  if (voiceState === 'recording' || voiceState === 'paused' || voiceState === 'transcribing') return;
  if (!conversationId) {
    // Session not ready — not a connectivity claim.
    setOffline(false);
    setSendError('retry');
    return;
  }

  const text = draft.trim();
  const files = pendingFiles;
  if (!text && !files.length) return;

  const outgoing =
    text ||
    (files.length > 1 ? 'Please analyze these attachments.' : 'Please analyze this attachment.');
  setDraft('');
  setPendingFiles([]);
  scrollToBottom();
  autoTitleFromOutgoing(outgoing);

  let attachmentIds: string[] | undefined;
  if (files.length) {
    try {
      const uploaded = await Promise.all(files.map((f) => uploadOwnerAttachment(f)));
      attachmentIds = uploaded.map((u) => u.attachment_id);
    } catch (err) {
      restoreDraft(setDraft, text, setPendingFiles, files);
      if (isNetworkFailure(err)) {
        setSendError(null);
        setOffline(true);
      } else {
        setOffline(false);
        setSendError('messageFailed');
      }
      return;
    }
  }

  const imageUris = files.filter((f) => isImageMime(f.mimeType)).map((f) => f.uri);
  if (imageUris.length) {
    imagePreviewByContent.current[outgoing] = imageUris;
  }

  const optimisticId = appendOptimisticUser(outgoing, imageUris.length ? imageUris : undefined);
  const result = await ownerSend(outgoing, { attachment_ids: attachmentIds });
  if (result === 'skipped' || result === 'error' || result === 'network_error') {
    removeOptimisticUser(optimisticId);
    restoreDraft(setDraft, text, setPendingFiles, files);
    if (result === 'network_error') {
      setSendError(null);
      setOffline(true);
    } else if (result === 'error') {
      setOffline(false);
      setSendError('messageFailed');
    } else {
      setOffline(false);
      setSendError('retry');
    }
    return;
  }
  if (result === 'cancelled') {
    // Stop leaves partial turn; keep draft cleared (user chose stop).
    setOffline(false);
    return;
  }
  setOffline(false);
  setSendError(null);
  scrollToBottom();
}
