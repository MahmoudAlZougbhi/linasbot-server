import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, fonts, radii, spacing } from '../../theme';
import type { VoiceState } from './useVoiceDraft';

type Props = {
  draft: string;
  onChangeDraft: (v: string) => void;
  onSend: () => void;
  onPlus: () => void;
  onToggleVoice: () => void;
  sending: boolean;
  voiceState: VoiceState;
};

export function ChatComposer({
  draft,
  onChangeDraft,
  onSend,
  onPlus,
  onToggleVoice,
  sending,
  voiceState,
}: Props) {
  const insets = useSafeAreaInsets();
  const micLabel =
    voiceState === 'recording' ? '■' : voiceState === 'transcribing' ? '…' : '🎙';

  return (
    <View style={[styles.wrap, { paddingBottom: Math.max(insets.bottom, 10) }]}>
      <Pressable style={styles.round} onPress={onPlus}>
        <Text style={styles.roundText}>+</Text>
      </Pressable>
      <TextInput
        style={styles.input}
        placeholder="Message Linas AI"
        placeholderTextColor={colors.textDim}
        value={draft}
        onChangeText={onChangeDraft}
        multiline
      />
      <Pressable
        style={styles.round}
        onPress={onToggleVoice}
        disabled={voiceState === 'transcribing'}
      >
        <Text style={styles.roundText}>{micLabel}</Text>
      </Pressable>
      <Pressable
        style={[styles.send, (!draft.trim() || sending) && styles.sendDisabled]}
        onPress={onSend}
        disabled={sending || !draft.trim()}
      >
        {sending ? (
          <ActivityIndicator color={colors.onAccent} />
        ) : (
          <Text style={styles.sendText}>↑</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.borderSoft,
    backgroundColor: colors.bgElevated,
  },
  round: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  roundText: { color: colors.accent, fontSize: 18, fontWeight: '700' },
  input: {
    flex: 1,
    minHeight: 42,
    maxHeight: 120,
    backgroundColor: colors.input,
    borderRadius: radii.lg,
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: colors.border,
  },
  send: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendDisabled: { opacity: 0.45 },
  sendText: { color: colors.onAccent, fontSize: 20, fontWeight: '800' },
});
