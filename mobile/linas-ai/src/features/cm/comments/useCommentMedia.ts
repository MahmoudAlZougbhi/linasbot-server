import { useState } from 'react';

import { ApiError } from '../../../api/client';
import type { StringKey } from '../../../i18n';
import { newId } from '../cmApi';
import { uploadCmArticleMedia } from '../cmMediaApi';
import { pickKnowledgeFile, pickKnowledgeImage, pickKnowledgeVideo } from '../knowledge/knowledgePick';
import {
  resourceMetaError,
  serializeResourceFields,
  suggestedTitleFromFilename,
} from '../resources/resourceMeta';
import { isValidHttpUrl, type CommentAttachment, type CommentKind, type CommentRuleItem } from './commentModel';

export type CommentResourcePrompt = {
  mode: 'create' | 'edit';
  kind: CommentKind;
  attachId?: string;
  replaceId?: string;
  preview: string;
  url: string;
  title: string;
  description: string;
  pending?: CommentAttachment;
};

export function useCommentMedia(
  selected: CommentRuleItem | null,
  patchSelected: (patch: Partial<Pick<CommentRuleItem, 'attachments'>>) => void,
  tr: (key: StringKey) => string,
) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<CommentResourcePrompt | null>(null);
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
    kind: CommentKind,
    replaceId?: string,
  ) {
    if (!selected || !picked) return;
    setUploading(true);
    setUploadError(null);
    try {
      const uploaded = await uploadCmArticleMedia(picked);
      const nextAtt: CommentAttachment = {
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
        mime: uploaded.mime || picked.mimeType,
        filename: uploaded.filename || picked.name,
        size: uploaded.size || 0,
        url: '',
        duration_seconds: picked.durationSeconds ?? null,
      };
      const existing = replaceId ? selected.attachments.find((row) => row.id === replaceId) : null;
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
    } catch (err) {
      setUploadError(failMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function addResource(kind: CommentKind, replaceId?: string) {
    if (kind === 'link') {
      const existing = replaceId ? selected?.attachments.find((row) => row.id === replaceId) : null;
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

  function editResource(att: CommentAttachment) {
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
    if (!selected || !prompt) return;
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
      const nextAtt: CommentAttachment = {
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
      const current = selected.attachments;
      const target = prompt.replaceId || prompt.attachId;
      const next = target ? current.map((row) => (row.id === target ? nextAtt : row)) : [...current, nextAtt];
      patchSelected({ attachments: next });
      setPrompt(null);
      setPromptError(null);
      setUploadError(null);
      return;
    }
    if (prompt.pending) {
      const nextAtt: CommentAttachment = { ...prompt.pending, ...meta };
      const current = selected.attachments;
      const next = prompt.replaceId
        ? current.map((row) => (row.id === prompt.replaceId ? { ...nextAtt, id: row.id } : row))
        : [...current, nextAtt];
      patchSelected({ attachments: next });
      setPrompt(null);
      setPromptError(null);
      return;
    }
    if (!prompt.attachId) return;
    patchSelected({
      attachments: selected.attachments.map((row) => (row.id === prompt.attachId ? { ...row, ...meta } : row)),
    });
    setPrompt(null);
    setPromptError(null);
  }

  return {
    uploading,
    uploadError,
    setUploadError,
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
