import type { ControlArea } from '../control/controlAreas';
import type { PlusAction } from './ComposerPlusSheet';
import {
  MAX_IMAGES,
  pickDocumentAttachment,
  pickImageAttachments,
  type PendingFile,
} from './v2/pickAttachment';

type Args = {
  action: PlusAction;
  isAuthenticated: boolean;
  pendingFiles: PendingFile[];
  setPendingFiles: (files: PendingFile[] | ((prev: PendingFile[]) => PendingFile[])) => void;
  onOpenArea: (area: ControlArea) => void;
};

export async function handlePlusAction({
  action,
  isAuthenticated,
  pendingFiles,
  setPendingFiles,
  onOpenArea,
}: Args): Promise<void> {
  if (!isAuthenticated) return;
  if (action === 'add_cm' || action === 'review_setup') {
    onOpenArea('cm');
    return;
  }
  if (action === 'check_usage') {
    onOpenArea('usage');
    return;
  }
  if (action === 'attach_image') {
    const picked = await pickImageAttachments(pendingFiles.length);
    if (!picked.length) return;
    setPendingFiles((prev) => [...prev, ...picked].slice(0, MAX_IMAGES));
    return;
  }
  if (action === 'attach_document') {
    if (pendingFiles.length >= MAX_IMAGES) return;
    const doc = await pickDocumentAttachment();
    if (doc) setPendingFiles((prev) => [...prev, doc].slice(0, MAX_IMAGES));
  }
}
