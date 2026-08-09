import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { z } from 'zod';

import { apiFetch, ApiError } from '../../api/client';
import { colors } from '../../theme/colors';

const KINDS = [
  { id: 'caption', label: 'Caption' },
  { id: 'post', label: 'Post' },
  { id: 'rewrite', label: 'Rewrite' },
  { id: 'campaign_ideas', label: 'Campaign ideas' },
  { id: 'image', label: 'Image (queued)' },
  { id: 'video', label: 'Video', disabled: true, note: 'Coming later — no production video provider' },
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
  const [output, setOutput] = useState<string>('');

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
      setOutput(JSON.stringify(data.result, null, 2));
    } catch (err) {
      setError(err instanceof ApiError ? `Failed (${err.status})` : 'Network error');
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.root}>
      <Pressable onPress={onBack}>
        <Text style={styles.link}>Back</Text>
      </Pressable>
      <Text style={styles.title}>Creative Studio</Text>
      <ScrollView horizontal contentContainerStyle={styles.kinds}>
        {KINDS.map((item) => (
          <Pressable
            key={item.id}
            style={[styles.chip, kind === item.id && styles.chipOn, 'disabled' in item && item.disabled && styles.chipOff]}
            onPress={() => setKind(item.id)}
          >
            <Text style={styles.chipText}>{item.label}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <TextInput
        style={styles.input}
        multiline
        placeholder="Describe what you want to create"
        placeholderTextColor={colors.textMuted}
        value={prompt}
        onChangeText={setPrompt}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable style={styles.button} onPress={() => void generate()} disabled={loading || !prompt.trim()}>
        {loading ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.buttonText}>Generate</Text>}
      </Pressable>
      <ScrollView>
        <Text style={styles.out}>{output}</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg, paddingTop: 56, paddingHorizontal: 16 },
  link: { color: colors.accent, marginBottom: 8 },
  title: { color: colors.text, fontSize: 28, fontWeight: '700', marginBottom: 12 },
  kinds: { gap: 8, paddingBottom: 12 },
  chip: {
    backgroundColor: colors.surface,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderColor: colors.border,
    borderWidth: 1,
    marginRight: 8,
  },
  chipOn: { borderColor: colors.accent },
  chipOff: { opacity: 0.5 },
  chipText: { color: colors.text, fontWeight: '600' },
  input: {
    minHeight: 100,
    backgroundColor: colors.input,
    borderRadius: 12,
    color: colors.text,
    padding: 12,
    marginBottom: 12,
    borderColor: colors.border,
    borderWidth: 1,
  },
  button: {
    backgroundColor: colors.accent,
    borderRadius: 12,
    padding: 14,
    alignItems: 'center',
    marginBottom: 12,
  },
  buttonText: { color: colors.bg, fontWeight: '700' },
  out: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 12 },
  error: { color: colors.danger, marginBottom: 8 },
});
