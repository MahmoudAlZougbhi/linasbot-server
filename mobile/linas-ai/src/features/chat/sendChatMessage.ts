import type { PendingFile } from './v2/pickAttachment';
import { isImageMime } from './v2/pickAttachment';
import { uploadOwnerAttachment } from './v2/useOwnerStream';
import type { VoiceState } from './useVoiceDraft';

type GuestSend = (
  content: string,
) => Promise<'done' | 'gated' | 'rejected' | 'error' | 'skipped'>;

type OwnerTurnSend = (
  text: string,
  opts?: { attachment_ids?: string[] },
) => Promise<'done' | 'error' | 'cancelled' | 'skipped'>;

type Args = {
  isAuthenticated: boolean;
  draft: string;
  setDraft: (v: string) => void;
  pendingFiles: PendingFile[];
  setPendingFiles: (files: PendingFile[] | ((prev: PendingFile[]) => PendingFile[])) => void;
  voiceState: VoiceState;
  conversationId: string | null;
  guestGated: boolean;
  guestQuestionsRemaining: number;
  guestSend: GuestSend;
  ownerSend: OwnerTurnSend;
  appendOptimisticUser: (content: string, localImageUris?: string[]) => string;
  removeOptimisticUser: (id: string) => void;
  autoTitleFromOutgoing: (content: string) => void;
  openAuthPreservingDraft: (hard?: boolean) => void;
  setOffline: (v: boolean) => void;
  scrollToBottom: () => void;
  imagePreviewByContent: { current: Record<string, string[]> };
};

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
    guestQuestionsRemaining,
    guestSend,
    ownerSend,
    appendOptimisticUser,
    removeOptimisticUser,
    autoTitleFromOutgoing,
    openAuthPreservingDraft,
    setOffline,
    scrollToBottom,
    imagePreviewByContent,
  } = args;

  if (!isAuthenticated) {
    if (guestGated || guestQuestionsRemaining <= 0) {
      openAuthPreservingDraft(true);
      return;
    }
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    scrollToBottom();
    const result = await guestSend(text);
    if (result === 'skipped' || result === 'rejected' || result === 'error') {
      setDraft(text);
      if (result === 'error') setOffline(true);
    }
    return;
  }

  if (voiceState === 'recording' || voiceState === 'transcribing') return;
  if (!conversationId) {
    setOffline(true);
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
    } catch {
      setDraft(text);
      setPendingFiles(files);
      setOffline(true);
      return;
    }
  }

  const imageUris = files.filter((f) => isImageMime(f.mimeType)).map((f) => f.uri);
  if (imageUris.length) {
    imagePreviewByContent.current[outgoing] = imageUris;
  }

  const optimisticId = appendOptimisticUser(outgoing, imageUris.length ? imageUris : undefined);
  const result = await ownerSend(outgoing, { attachment_ids: attachmentIds });
  if (result === 'skipped' || result === 'error') {
    removeOptimisticUser(optimisticId);
    setDraft(text);
    setPendingFiles(files);
    if (result === 'error') setOffline(true);
    return;
  }
  scrollToBottom();
}
