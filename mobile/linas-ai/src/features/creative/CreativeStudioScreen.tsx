import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { z } from 'zod';

import { apiFetch, ApiError } from '../../api/client';
import { PrimaryButton } from '../../components/PrimaryButton';
import { StatusChip } from '../../components/StatusChip';
import { TextField } from '../../components/TextField';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

const KINDS = [
  { id: 'caption', label: 'Caption' },
  { id: 'post', label: 'Post' },
  { id: 'rewrite', label: 'Rewrite' },
  { id: 'campaign_ideas', label: 'Campaign ideas' },
  { id: 'image', label: 'Image', note: 'Image generation may take a moment' },
  { id: 'video', label: 'Video', disabled: true, note: 'Video generation is coming soon' },
] as const;

const ResultSchema = z.object({
  success: z.literal(true),
  result: z.record(z.string(), z.unknown()),
});

type Props = { onBack: () => void };

export function CreativeStudioScreen({ onBack }: Props) {
  const [kind, setKind] = useState<(typeof KINDS)[number]['id']>('caption');
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [output, setOutput] = useState('');

  async function generate() {
    const selected = KINDS.find((k) => k.id === kind);
    if (selected && 'disabled' in selected && selected.disabled) {
      setError(selected.note);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch('/api/creative/generate', {
        method: 'POST',
        body: JSON.stringify({ kind, prompt: prompt.trim() }),
        schema: ResultSchema,
      });
      const result = data.result;
      const textBits = Object.values(result).filter((v): v is string => typeof v === 'string');
      setOutput(
        textBits.join('\n\n') || (__DEV__ ? JSON.stringify(result, null, 2) : 'Done.'),
      );
    } catch (err) {
      setError(err instanceof ApiError ? 'Something went wrong. Please try again.' : 'Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScreenChrome title="Creative Studio" subtitle="Full studio workspace" onBack={onBack}>
      <ScrollView horizontal contentContainerStyle={styles.kinds} showsHorizontalScrollIndicator={false}>
        {KINDS.map((item) => {
          const disabled = 'disabled' in item && item.disabled;
          return (
            <Pressable
              key={item.id}
              style={[styles.chip, kind === item.id && styles.chipOn, disabled && styles.chipOff]}
              onPress={() => setKind(item.id)}
            >
              <Text style={styles.chipText}>{item.label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
      {kind === 'video' ? <StatusChip label="Coming soon" tone="soon" /> : null}
      <TextField
        multiline
        placeholder="Describe what you want to create"
        value={prompt}
        onChangeText={setPrompt}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <PrimaryButton
        label="Generate"
        onPress={() => void generate()}
        loading={loading}
        disabled={!prompt.trim()}
      />
      <ScrollView style={styles.outScroll}>
        <Text style={styles.out}>{output}</Text>
      </ScrollView>
      {loading ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : null}
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  kinds: { gap: 8, paddingBottom: spacing.md },
  chip: {
    backgroundColor: colors.surface,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderColor: colors.border,
    borderWidth: 1,
    marginRight: 8,
  },
  chipOn: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  chipOff: { opacity: 0.5 },
  chipText: { color: colors.text, fontFamily: fonts.bodyMedium },
  outScroll: { marginTop: spacing.lg },
  out: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 12 },
  error: { color: colors.danger, marginBottom: spacing.sm, fontFamily: fonts.body },
  loading: { marginTop: spacing.md },
});
