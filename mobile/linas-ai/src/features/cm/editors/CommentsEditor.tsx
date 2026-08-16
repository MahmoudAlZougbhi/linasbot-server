import { Text, View } from 'react-native';
import { useEffect, useState } from 'react';
import { z } from 'zod';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { apiFetch } from '../../../api/client';
import { asRecordList, newId } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';
import { OptionPicker } from './OptionPicker';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

const AccountsSchema = z.object({ success: z.boolean(), accounts: z.array(z.record(z.string(), z.unknown())).optional() }).passthrough();
const PreviewSchema = z.object({ success: z.boolean(), preview: z.record(z.string(), z.unknown()).optional() }).passthrough();

const RULE_MODES = ['Automated / No AI', 'AI-guided'] as const;
const SCOPES = ['All Posts', 'Specific Post'] as const;
const TRIGGERS = ['All Comments', 'Exact text', 'Contains any', 'Contains all', 'Keywords'] as const;
const DET_ACTIONS = ['Ignore', 'Reply on Comment', 'Send DM', 'Comment + DM'] as const;
const AI_ACTIONS = ['Reply on Comment', 'Send DM', 'Comment + DM'] as const;

function modeValue(label: string): 'deterministic' | 'ai_guidance' {
  return label === 'AI-guided' ? 'ai_guidance' : 'deterministic';
}

function scopeValue(label: string): 'all_posts' | 'specific_post' {
  return label === 'Specific Post' ? 'specific_post' : 'all_posts';
}

function triggerValue(label: string): string {
  if (label === 'All Comments') return 'all_comments';
  if (label === 'Exact text') return 'exact_text';
  if (label === 'Contains all') return 'contains_all';
  if (label === 'Keywords') return 'keyword_set';
  return 'contains_any';
}

function detActionValue(label: string): string {
  if (label === 'Ignore') return 'ignore';
  if (label === 'Send DM') return 'send_dm_static';
  if (label === 'Comment + DM') return 'reply_comment_and_dm_static';
  return 'reply_comment_static';
}

function aiActionValue(label: string): string {
  if (label === 'Send DM') return 'send_dm';
  if (label === 'Comment + DM') return 'reply_comment_and_dm';
  return 'reply_comment';
}

function labelOf(map: Record<string, string>, value: string, fallback: string): string {
  return map[value] || fallback;
}

const TRIGGER_LABELS: Record<string, string> = {
  all_comments: 'All Comments',
  exact_text: 'Exact text',
  contains_all: 'Contains all',
  keyword_set: 'Keywords',
  contains_any: 'Contains any',
};

export function CommentsEditor({ payload, onChange }: Props) {
  const rules = asRecordList(payload.rules);
  const [accounts, setAccounts] = useState<Array<Record<string, string>>>([]);
  const [previewText, setPreviewText] = useState('');
  const [previewResult, setPreviewResult] = useState('');

  useEffect(() => {
    void apiFetch('/api/cm/comment-rules/accounts', { schema: AccountsSchema })
      .then((data) => {
        const rows = Array.isArray(data.accounts) ? data.accounts : [];
        setAccounts(rows.map((row) => ({
          platform: String(row.platform || ''),
          connected_account_id: String(row.connected_account_id || ''),
          page_or_ig_account_id: String(row.page_or_ig_account_id || ''),
          name: String(row.name || ''),
        })));
      })
      .catch(() => setAccounts([]));
  }, []);

  const setRules = (next: Record<string, unknown>[]) => onChange({ ...payload, rules: next });

  const add = () => {
    const id = newId('crule');
    setRules([
      {
        id,
        enabled: true,
        name: 'New rule',
        scope: 'all_posts',
        rule_mode: 'deterministic',
        trigger_type: 'contains_any',
        priority: 10,
        revision: 1,
        match_mode: 'any_keyword',
        keywords: [],
        pattern: '',
        post_id: '',
        platform: 'instagram',
        connected_account_id: '',
        page_or_ig_account_id: '',
        channel: 'any',
        action: 'reply_comment_static',
        reply_template: '',
        dm_template: '',
        ai_instructions: '',
        ai_action_mode: 'reply_comment',
        notes: null,
      },
      ...rules,
    ]);
  };

  const patch = (id: string, patchData: Record<string, unknown>) =>
    setRules(rules.map((item) => (String(item.id) === id ? { ...item, ...patchData } : item)));

  const runPreview = async (item: Record<string, unknown>) => {
    try {
      const data = await apiFetch('/api/cm/comment-rules/preview', {
        method: 'POST',
        schema: PreviewSchema,
        body: JSON.stringify({
          rule: item,
          comment_text: previewText,
          post_id: String(item.post_id || ''),
          channel: String(item.channel || ''),
          account_id: String(item.connected_account_id || ''),
        }),
      });
      const preview = data.preview || {};
      setPreviewResult(preview.matched ? `Match → ${String(preview.action || '')}` : 'No match');
    } catch {
      setPreviewResult('Preview failed');
    }
  };

  return (
    <View>
      <Field
        label="Default when no rule matches"
        value={String(payload.default_action || 'reply_comment')}
        onChange={(v) => onChange({ ...payload, default_action: v === 'ignore' ? 'ignore' : 'reply_comment' })}
        hint="AI replies on the comment, or ignore"
      />
      <PrimaryButton label="Add comment rule" onPress={add} variant="ghost" />
      <View style={{ height: 12 }} />
      {rules.map((item) => {
        const id = String(item.id);
        const mode = String(item.rule_mode || 'deterministic');
        const scope = String(item.scope || (item.post_id ? 'specific_post' : 'all_posts'));
        return (
          <View key={id} style={cmFormStyles.card}>
            <Field label="Title" value={String(item.name || '')} onChange={(v) => patch(id, { name: v })} />
            <OptionPicker
              label="Scope"
              value={scope === 'specific_post' ? 'Specific Post' : 'All Posts'}
              options={[...SCOPES]}
              onChange={(v) => patch(id, { scope: scopeValue(v), post_id: scopeValue(v) === 'all_posts' ? '' : item.post_id })}
            />
            {scope === 'specific_post' ? (
              <>
                <OptionPicker
                  label="Connected account"
                  value={
                    accounts.find((a) => a.connected_account_id === String(item.connected_account_id || ''))?.name ||
                    String(item.connected_account_id || '')
                  }
                  options={accounts.map((a) => a.name || a.connected_account_id)}
                  onChange={(name) => {
                    const acc = accounts.find((a) => (a.name || a.connected_account_id) === name);
                    if (!acc) return;
                    patch(id, {
                      platform: acc.platform,
                      connected_account_id: acc.connected_account_id,
                      page_or_ig_account_id: acc.page_or_ig_account_id,
                      channel: acc.platform,
                    });
                  }}
                />
                <Field
                  label="Post ID"
                  value={String(item.post_id || '')}
                  onChange={(v) => patch(id, { post_id: v })}
                  hint="Pick a post from this connected account only"
                />
              </>
            ) : null}
            <OptionPicker
              label="Rule type"
              value={mode === 'ai_guidance' ? 'AI-guided' : 'Automated / No AI'}
              options={[...RULE_MODES]}
              onChange={(v) => patch(id, { rule_mode: modeValue(v) })}
            />
            <OptionPicker
              label="Trigger"
              value={labelOf(TRIGGER_LABELS, String(item.trigger_type || 'contains_any'), 'Contains any')}
              options={[...TRIGGERS]}
              onChange={(v) => patch(id, { trigger_type: triggerValue(v) })}
            />
            {String(item.trigger_type || '') !== 'all_comments' ? (
              <Field
                label="Keywords / text"
                value={Array.isArray(item.keywords) ? item.keywords.map(String).join(', ') : ''}
                onChange={(v) =>
                  patch(id, {
                    keywords: v
                      .split(',')
                      .map((x) => x.trim())
                      .filter(Boolean),
                  })
                }
              />
            ) : null}
            {mode === 'ai_guidance' ? (
              <>
                <OptionPicker
                  label="AI action"
                  value={
                    String(item.ai_action_mode) === 'send_dm'
                      ? 'Send DM'
                      : String(item.ai_action_mode) === 'reply_comment_and_dm'
                        ? 'Comment + DM'
                        : 'Reply on Comment'
                  }
                  options={[...AI_ACTIONS]}
                  onChange={(v) => patch(id, { ai_action_mode: aiActionValue(v), action: aiActionValue(v) })}
                />
                <Field
                  label="AI instructions"
                  value={String(item.ai_instructions || '')}
                  onChange={(v) => patch(id, { ai_instructions: v })}
                  multiline
                />
              </>
            ) : (
              <>
                <OptionPicker
                  label="Automated action"
                  value={
                    String(item.action) === 'ignore' || String(item.static_action) === 'ignore'
                      ? 'Ignore'
                      : String(item.action).includes('dm') && String(item.action).includes('comment')
                        ? 'Comment + DM'
                        : String(item.action).includes('dm')
                          ? 'Send DM'
                          : 'Reply on Comment'
                  }
                  options={[...DET_ACTIONS]}
                  onChange={(v) => patch(id, { action: detActionValue(v), static_action: detActionValue(v) })}
                />
                <Field
                  label="Static comment text"
                  value={String(item.reply_template || '')}
                  onChange={(v) => patch(id, { reply_template: v })}
                  multiline
                />
                <Field
                  label="Static DM text"
                  value={String(item.dm_template || '')}
                  onChange={(v) => patch(id, { dm_template: v })}
                  multiline
                />
              </>
            )}
            <Field
              label="Priority (higher wins)"
              value={String(item.priority ?? 0)}
              onChange={(v) => patch(id, { priority: Number(v) || 0 })}
            />
            <Field label="Test comment" value={previewText} onChange={setPreviewText} />
            <PrimaryButton label="Preview / Test Rule" variant="ghost" onPress={() => void runPreview(item)} />
            {previewResult ? <Text style={cmFormStyles.hint}>{previewResult}</Text> : null}
            <Text style={cmFormStyles.hint}>
              {item.enabled === false ? 'Inactive' : 'Active'} · {scope} · {mode}
            </Text>
            <PrimaryButton
              label={item.enabled === false ? 'Enable rule' : 'Disable rule'}
              variant="ghost"
              onPress={() => patch(id, { enabled: item.enabled === false })}
            />
            <PrimaryButton
              label="Delete rule"
              variant="ghost"
              onPress={() => setRules(rules.filter((r) => String(r.id) !== id))}
            />
          </View>
        );
      })}
      {rules.length === 0 ? <Text style={cmFormStyles.hint}>No rules — uses default Customer AI flow.</Text> : null}
    </View>
  );
}
