import { uploadCmArticleMedia, type CmMediaUploadResult } from './cmMediaApi';

export type PickedCmMedia = {
  uri: string;
  name: string;
  mimeType: string;
  durationSeconds?: number;
};

/** Upload picked CM media and always clear the uploading spinner. */
export async function runCmMediaUpload(params: {
  picked: PickedCmMedia | null;
  failMessage: (err: unknown) => string;
  setUploading: (value: boolean) => void;
  setUploadError: (value: string | null) => void;
  onSuccess: (uploaded: CmMediaUploadResult, picked: PickedCmMedia) => void;
}): Promise<void> {
  const { picked, failMessage, setUploading, setUploadError, onSuccess } = params;
  if (!picked) return;
  setUploading(true);
  setUploadError(null);
  try {
    const uploaded = await uploadCmArticleMedia(picked);
    onSuccess(uploaded, picked);
  } catch (err) {
    setUploadError(failMessage(err));
  } finally {
    setUploading(false);
  }
}
