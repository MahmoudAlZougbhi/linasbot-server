import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';
import { File } from 'expo-file-system';
import { EncodingType, readAsStringAsync } from 'expo-file-system/legacy';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { TextField } from '../../components/TextField';
import { colors, fonts, radii, spacing } from '../../theme';

type Props = {
  disabled?: boolean;
  busy?: boolean;
  readOnlyReason?: string | null;
  onSendText: (text: string) => Promise<boolean>;
  onSendMedia: (base64: string, type: 'voice' | 'image') => Promise<boolean>;
};

export function LiveChatComposer({
  disabled,
  busy,
  readOnlyReason,
  onSendText,
  onSendMedia,
}: Props) {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const [mediaError, setMediaError] = useState<string | null>(null);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);

  if (readOnlyReason) {
    return (
      <View style={styles.readonly}>
        <Text style={styles.readonlyText}>{readOnlyReason}</Text>
      </View>
    );
  }

  async function sendText() {
    const value = text.trim();
    if (!value || busy || disabled) return;
    const ok = await onSendText(value);
    if (ok) setText('');
  }

  async function toggleVoice() {
    setMediaError(null);
    if (recording) {
      try {
        await recorder.stop();
        setRecording(false);
        const uri = recorder.uri;
        if (!uri) throw new Error('No recording');
        const base64 = await readAsStringAsync(uri, { encoding: EncodingType.Base64 });
        await onSendMedia(base64, 'voice');
      } catch {
        setMediaError('Could not send voice message.');
      } finally {
        await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      }
      return;
    }
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        setMediaError('Microphone permission is required.');
        return;
      }
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRecording(true);
    } catch {
      setMediaError('Could not start recording.');
    }
  }

  async function pickImage() {
    setMediaError(null);
    try {
      const picked = await File.pickFileAsync({ mimeTypes: ['image/*'] });
      if (picked.canceled || !picked.result) return;
      const file = Array.isArray(picked.result) ? picked.result[0] : picked.result;
      if (!file) {
        setMediaError('No image selected.');
        return;
      }
      const base64 = await file.base64();
      await onSendMedia(base64, 'image');
    } catch {
      setMediaError('Could not send image.');
    }
  }

  return (
    <View style={styles.wrap}>
      {mediaError ? <Text style={styles.error}>{mediaError}</Text> : null}
      <TextField
        value={text}
        onChangeText={setText}
        placeholder="Reply as human…"
        editable={!disabled && !busy && !recording}
        style={styles.input}
      />
      <View style={styles.actions}>
        <Pressable
          style={[styles.btn, styles.ghost]}
          onPress={() => void toggleVoice()}
          disabled={busy || disabled}
        >
          <Text style={styles.ghostLabel}>{recording ? 'Stop & send' : 'Voice'}</Text>
        </Pressable>
        <Pressable
          style={[styles.btn, styles.ghost]}
          onPress={() => void pickImage()}
          disabled={busy || disabled || recording}
        >
          <Text style={styles.ghostLabel}>Image</Text>
        </Pressable>
        <Pressable
          style={[styles.btn, styles.primary, (busy || disabled || !text.trim()) && styles.disabled]}
          onPress={() => void sendText()}
          disabled={busy || disabled || !text.trim() || recording}
        >
          <Text style={styles.primaryLabel}>{busy ? '…' : 'Send'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
    gap: spacing.sm,
    backgroundColor: colors.bg,
  },
  input: { marginBottom: 0 },
  actions: { flexDirection: 'row', gap: spacing.sm },
  btn: {
    borderRadius: radii.md,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ghost: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  primary: { backgroundColor: colors.accent, flex: 1 },
  disabled: { opacity: 0.45 },
  ghostLabel: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 14 },
  primaryLabel: { color: colors.onAccent, fontFamily: fonts.bodyMedium, fontSize: 14 },
  error: { color: colors.danger, fontFamily: fonts.body, fontSize: 12 },
  readonly: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingVertical: spacing.md,
  },
  readonlyText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
});
