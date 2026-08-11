import { useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import {
  pickDocumentAttachment,
  pickImageAttachment,
} from '../../chat/v2/pickAttachment';
import { asRecordList, newId } from '../cmApi';
import { uploadCmArticleMedia } from '../cmMediaApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  section: 'knowledge' | 'care';
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

type AttachmentRow = {
  id: string;
  kind: string;
  caption: string;
  mime: string;
  filename: string;
  size: number;
};

function asAttachments(value: unknown): AttachmentRow[] {
  return asRecordList(value).map((row) => ({
    id: String(row.id || ''),
    kind: String(row.kind || 'file'),
    caption: String(row.caption || ''),
    mime: String(row.mime || ''),
    filename: String(row.filename || ''),
    size: typeof row.size === 'number' ? row.size : 0,
  }));
}

export function ArticlesEditor({ section, payload, onChange }: Props) {
  const items = asRecordList(payload.items);
  const [selectedId, setSelectedId] = useState<string | null>(
    items[0] ? String(items[0].id) : null,
  );
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const selected = items.find((item) => String(item.id) === selectedId) || items[0] || null;

  const setItems = (next: Record<string, unknown>[]) => onChange({ ...payload, items: next });

  const add = () => {
    const id = newId(section);
    setItems([
      {
        id,
        title: '',
        body: '',
        tags: [],
        language: '',
        audience: 'general',
        category: '',
        status: 'active',
        source_filename: null,
        source_checksum: null,
        linked_service_ids: [],
        linked_branch_ids: [],
        notes: null,
        attachments: [],
      },
      ...items,
    ]);
    setSelectedId(id);
  };

  const patch = (id: string, patchData: Record<string, unknown>) =>
    setItems(items.map((item) => (String(item.id) === id ? { ...item, ...patchData } : item)));

  const attachments = selected ? asAttachments(selected.attachments) : [];

  const setAttachments = (next: AttachmentRow[]) => {
    if (!selected) return;
    patch(String(selected.id), { attachments: next });
  };

  const attachPicked = async (picked: { uri: string; name: string; mimeType: string } | null) => {
    if (!selected || !picked) return;
    setUploading(true);
    setUploadError(null);
    try {
      const uploaded = await uploadCmArticleMedia(picked);
      setAttachments([
        ...attachments,
        {
          id: uploaded.media_id,
          kind: uploaded.kind || (picked.mimeType.startsWith('image/') ? 'image' : 'file'),
          caption: '',
          mime: uploaded.mime || picked.mimeType,
          filename: uploaded.filename || picked.name,
          size: uploaded.size || 0,
        },
      ]);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <View>
      <PrimaryButton label="Add article" onPress={add} variant="ghost" />
      <View style={{ height: 12 }} />
      {items.map((item) => {
        const id = String(item.id);
        const active = selected && String(selected.id) === id;
        return (
          <Pressable
            key={id}
            style={[cmFormStyles.itemCard, active && { borderColor: '#2563EB' }]}
            onPress={() => setSelectedId(id)}
          >
            <Text style={cmFormStyles.itemTitle}>{String(item.title || id)}</Text>
          </Pressable>
        );
      })}
      {selected ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Title"
            value={String(selected.title || '')}
            onChange={(v) => patch(String(selected.id), { title: v })}
          />
          <Field
            label="Note"
            value={String(selected.body || '')}
            onChange={(v) => patch(String(selected.id), { body: v })}
            multiline
            hint="Stored as article body in the CM draft."
          />
          <Text style={[cmFormStyles.hint, { marginTop: 12, marginBottom: 8 }]}>
            Case examples — attach an image/file and write when the AI should use it
            (e.g. “filled form for intake”, “send this PDF for package A”).
          </Text>
          {attachments.map((att, index) => (
            <View key={att.id || `${index}`} style={{ marginBottom: 10 }}>
              <Text style={cmFormStyles.itemTitle}>
                {att.kind}: {att.filename || att.id}
              </Text>
              <Field
                label="When to use (caption)"
                value={att.caption}
                onChange={(v) => {
                  const next = attachments.map((row, i) =>
                    i === index ? { ...row, caption: v } : row,
                  );
                  setAttachments(next);
                }}
                multiline
              />
              <PrimaryButton
                label="Remove attachment"
                variant="ghost"
                onPress={() => setAttachments(attachments.filter((_, i) => i !== index))}
              />
            </View>
          ))}
          {uploading ? <ActivityIndicator style={{ marginVertical: 8 }} /> : null}
          {uploadError ? <Text style={{ color: '#B91C1C', marginBottom: 8 }}>{uploadError}</Text> : null}
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <PrimaryButton
              label="Add image"
              variant="ghost"
              onPress={() => void pickImageAttachment().then((f) => attachPicked(f))}
            />
            <PrimaryButton
              label="Add file"
              variant="ghost"
              onPress={() => void pickDocumentAttachment().then((f) => attachPicked(f))}
            />
          </View>
        </View>
      ) : (
        <Text style={cmFormStyles.hint}>No articles yet.</Text>
      )}
    </View>
  );
}
