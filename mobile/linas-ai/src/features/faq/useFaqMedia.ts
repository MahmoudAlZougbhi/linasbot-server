import { useState } from 'react';

import { ApiError } from '../../api/client';
import type { StringKey } from '../../i18n';
import { newId } from '../cm/cmApi';
import { runCmMediaUpload } from '../cm/cmMediaAttach';
import { pickKnowledgeFile, pickKnowledgeImage, pickKnowledgeVideo } from '../cm/knowledge/knowledgePick';
import {
  isValidHttpUrl,
  type KnowledgeAttachment,
  type KnowledgeKind,
} from '../cm/knowledge/knowledgeModel';
import {
  resourceMetaError,
  serializeResourceFields,
  suggestedTitleFromFilename,
} from '../cm/resources/resourceMeta';

export type FaqResourcePrompt = {
  mode: 'create' | 'edit';
  kind: KnowledgeKind;
  attachId?: string;
  replaceId?: string;
  preview: string;
  url: string;
  title: string;
  description: string;
  pending?: KnowledgeAttachment;
};

export function useFaqMedia(
  attachments: KnowledgeAttachment[],
  persist: (next: KnowledgeAttachment[]) => void,
  tr: (key: StringKey) => string,
) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<FaqResourcePrompt | null>(null);
  const [promptError, setPromptError] = useState<string | null>(null);

  function failMessage(err: unknown): string {
    const detail =
      err instanceof ApiError && err.body && typeof err.body === 'object' && 'detail' in err.body
        ? JSON.stringify((err.body as { detail: unknown }).detail)
        : err instanceof Error
          ? err.message
          : '';
    if (detail.includes('file_too_large')) return tr('commentsVideoTooLarge');
    if (detail.includes('unsupported_mime')) return tr('commentsUnsupported');
    return tr('commentsUploadFailed');
  }

  async function attachPicked(
    picked: { uri: string; name: string; mimeType: string; durationSeconds?: number } | null,
    kind: KnowledgeKind,
    replaceId?: string,
  ) {
    if (!picked) return;
    await runCmMediaUpload({
      picked,
      failMessage,
      setUploading,
      setUploadError,
      onSuccess: (uploaded, file) => {
      const nextAtt: KnowledgeAttachment = {
        id: uploaded.media_id,
        kind:
          uploaded.kind === 'image' || uploaded.kind === 'video'
            ? uploaded.kind
            : kind === 'video' || kind === 'image'
              ? kind
              : 'file',
        title: '',
        description: '',
        caption: '',
        mime: uploaded.mime || file.mimeType,
        filename: uploaded.filename || file.name,
        size: uploaded.size || 0,
        url: '',
        duration_seconds: file.durationSeconds ?? null,
      };
      const existing = replaceId ? attachments.find((row) => row.id === replaceId) : null;
      setPrompt({
        mode: replaceId ? 'edit' : 'create',
        kind: nextAtt.kind,
        replaceId,
        attachId: replaceId,
        preview: nextAtt.filename,
        url: '',
        title: existing?.title || suggestedTitleFromFilename(nextAtt.filename),
        description: existing?.description || existing?.caption || '',
        pending: nextAtt,
      });
      setPromptError(null);
      },
    });
  }

  async function addResource(kind: KnowledgeKind, replaceId?: string) {
    if (kind === 'link') {
      const existing = replaceId ? attachments.find((row) => row.id === replaceId) : null;
      setPrompt({
        mode: replaceId ? 'edit' : 'create',
        kind: 'link',
        replaceId,
        attachId: replaceId,
        preview: existing?.filename || '',
        url: existing?.url || '',
        title: existing?.title || '',
        description: existing?.description || existing?.caption || '',
      });
      setPromptError(null);
      return;
    }
    if (kind === 'image') {
      await attachPicked(await pickKnowledgeImage(), 'image', replaceId);
      return;
    }
    if (kind === 'video') {
      await attachPicked(await pickKnowledgeVideo(), 'video', replaceId);
      return;
    }
    await attachPicked(await pickKnowledgeFile(), 'file', replaceId);
  }

  function editResource(att: KnowledgeAttachment) {
    setPrompt({
      mode: 'edit',
      kind: att.kind,
      attachId: att.id,
      preview: att.filename || att.url,
      url: att.url,
      title: att.title,
      description: att.description || att.caption,
    });
    setPromptError(null);
  }

  function commitPrompt() {
    if (!prompt) return;
    const err = resourceMetaError(prompt.kind, { title: prompt.title, description: prompt.description }, prompt.url);
    if (err === 'title') {
      setPromptError(tr('resourceTitleRequired'));
      return;
    }
    if (err === 'description') {
      setPromptError(tr('resourceDescriptionRequired'));
      return;
    }
    if (err === 'url' || (prompt.kind === 'link' && !isValidHttpUrl(prompt.url))) {
      setPromptError(tr('commentsLinkInvalid'));
      return;
    }
    const meta = serializeResourceFields({ title: prompt.title, description: prompt.description });
    if (prompt.kind === 'link') {
      const url = prompt.url.trim();
      let host = url;
      try {
        host = new URL(url).hostname;
      } catch {
        host = url;
      }
      const nextAtt: KnowledgeAttachment = {
        id: prompt.replaceId || prompt.attachId || newId('link'),
        kind: 'link',
        title: meta.title,
        description: meta.description,
        caption: meta.caption,
        mime: '',
        filename: host,
        size: 0,
        url,
        duration_seconds: null,
      };
      const target = prompt.replaceId || prompt.attachId;
      persist(target ? attachments.map((row) => (row.id === target ? nextAtt : row)) : [...attachments, nextAtt]);
      setPrompt(null);
      setPromptError(null);
      setUploadError(null);
      return;
    }
    if (prompt.pending) {
      const nextAtt: KnowledgeAttachment = { ...prompt.pending, ...meta };
      persist(
        prompt.replaceId
          ? attachments.map((row) => (row.id === prompt.replaceId ? { ...nextAtt, id: row.id } : row))
          : [...attachments, nextAtt],
      );
      setPrompt(null);
      setPromptError(null);
      return;
    }
    if (!prompt.attachId) return;
    persist(attachments.map((row) => (row.id === prompt.attachId ? { ...row, ...meta } : row)));
    setPrompt(null);
    setPromptError(null);
  }

  return {
    uploading,
    uploadError,
    prompt,
    promptError,
    setPrompt,
    addResource,
    editResource,
    commitPrompt,
    closePrompt: () => {
      setPrompt(null);
      setPromptError(null);
    },
  };
}
