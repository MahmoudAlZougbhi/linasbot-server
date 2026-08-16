import { useState } from 'react';

import { ApiError } from '../../api/client';
import type { StringKey } from '../../i18n';
import { newId } from '../cm/cmApi';
import { uploadCmArticleMedia } from '../cm/cmMediaApi';
import { isValidHttpUrl, type ServiceAttachment, type ServiceItem, type ServiceKind } from './serviceModel';
import { pickServiceFile, pickServiceImage, pickServiceVideo } from './servicePick';

export type ServicePrompt = { kind: 'link' | 'caption'; attachId?: string; replaceId?: string };

export function useServiceMedia(
  selected: ServiceItem | null,
  patchSelected: (patch: Partial<Pick<ServiceItem, 'attachments'>>) => void,
  tr: (key: StringKey) => string,
) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<ServicePrompt | null>(null);
  const [promptValue, setPromptValue] = useState('');

  function failMessage(err: unknown): string {
    const detail =
      err instanceof ApiError && err.body && typeof err.body === 'object' && 'detail' in err.body
        ? JSON.stringify((err.body as { detail: unknown }).detail)
        : err instanceof Error
          ? err.message
          : '';
    if (detail.includes('file_too_large')) return tr('servicesVideoTooLarge');
    if (detail.includes('unsupported_mime')) return tr('servicesUnsupported');
    return tr('servicesUploadFailed');
  }

  async function attachPicked(
    picked: { uri: string; name: string; mimeType: string; durationSeconds?: number } | null,
    kind: ServiceKind,
    replaceId?: string,
  ) {
    if (!selected || !picked) return;
    setUploading(true);
    setUploadError(null);
    try {
      const uploaded = await uploadCmArticleMedia(picked);
      const nextAtt: ServiceAttachment = {
        id: uploaded.media_id,
        kind:
          uploaded.kind === 'image' || uploaded.kind === 'video'
            ? uploaded.kind
            : kind === 'video' || kind === 'image'
              ? kind
              : 'file',
        caption: '',
        mime: uploaded.mime || picked.mimeType,
        filename: uploaded.filename || picked.name,
        size: uploaded.size || 0,
        url: '',
        duration_seconds: picked.durationSeconds ?? null,
      };
      const current = selected.attachments;
      const next = replaceId
        ? current.map((row) => (row.id === replaceId ? { ...nextAtt, caption: row.caption } : row))
        : [...current, nextAtt];
      patchSelected({ attachments: next });
    } catch (err) {
      setUploadError(failMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function addResource(kind: ServiceKind, replaceId?: string) {
    if (kind === 'link') {
      const existing = replaceId ? selected?.attachments.find((row) => row.id === replaceId) : null;
      setPrompt({ kind: 'link', replaceId });
      setPromptValue(existing?.url || '');
      return;
    }
    if (kind === 'image') {
      await attachPicked(await pickServiceImage(), 'image', replaceId);
      return;
    }
    if (kind === 'video') {
      await attachPicked(await pickServiceVideo(), 'video', replaceId);
      return;
    }
    await attachPicked(await pickServiceFile(), 'file', replaceId);
  }

  function commitPrompt() {
    if (!selected || !prompt) return;
    if (prompt.kind === 'link') {
      if (!isValidHttpUrl(promptValue)) {
        setUploadError(tr('servicesLinkInvalid'));
        return;
      }
      const url = promptValue.trim();
      let host = url;
      try {
        host = new URL(url).hostname;
      } catch {
        host = url;
      }
      const nextAtt: ServiceAttachment = {
        id: prompt.replaceId || newId('link'),
        kind: 'link',
        caption: '',
        mime: '',
        filename: host,
        size: 0,
        url,
        duration_seconds: null,
      };
      const current = selected.attachments;
      const next = prompt.replaceId
        ? current.map((row) => (row.id === prompt.replaceId ? { ...nextAtt, caption: row.caption } : row))
        : [...current, nextAtt];
      patchSelected({ attachments: next });
      setPrompt(null);
      setPromptValue('');
      setUploadError(null);
      return;
    }
    if (!prompt.attachId) return;
    patchSelected({
      attachments: selected.attachments.map((row) =>
        row.id === prompt.attachId ? { ...row, caption: promptValue } : row,
      ),
    });
    setPrompt(null);
    setPromptValue('');
  }

  return {
    uploading,
    uploadError,
    setUploadError,
    prompt,
    promptValue,
    setPromptValue,
    setPrompt,
    addResource,
    commitPrompt,
    closePrompt: () => {
      setPrompt(null);
      setPromptValue('');
    },
  };
}
