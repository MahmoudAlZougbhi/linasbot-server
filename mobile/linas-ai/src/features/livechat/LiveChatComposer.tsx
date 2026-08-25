import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { useLiveChatOperatorMedia } from './useLiveChatOperatorMedia';

type Props = {
  onSend: (text: string) => Promise<boolean>;
  onSendMedia?: (base64: string, type: 'voice' | 'image') => Promise<boolean>;
  busy: boolean;
  disabled?: boolean;
};

export function LiveChatComposer({ onSend, onSendMedia, busy, disabled }: Props) {
  const { colors } = useTheme();
  const [draft, setDraft] = useState('');
  const media = useLiveChatOperatorMedia();
  const blocked = disabled || busy || media.isRecordingVoice;
  const canSend = !blocked && draft.trim().length > 0;

  const submit = async () => {
    const text = draft.trim();
    if (!text || busy || disabled) return;
    const ok = await onSend(text);
    if (ok) setDraft('');
  };

  const sendImage = async () => {
    if (blocked || !onSendMedia) return;
    const base64 = await media.pickImageBase64();
    if (!base64) return;
    await onSendMedia(base64, 'image');
  };

  const toggleVoice = async () => {
    if (disabled || busy || !onSendMedia) return;
    if (media.isRecordingVoice) {
      const base64 = await media.stopVoiceRecording();
      if (base64) await onSendMedia(base64, 'voice');
      return;
    }
    await media.startVoiceRecording();
  };

  return (
    <View>
      {media.mediaError ? (
        <Text style={[styles.hint, { color: colors.danger }]}>{media.mediaError}</Text>
      ) : null}
      {media.isRecordingVoice ? (
        <View style={styles.recordingRow}>
          <Text style={[styles.hint, { color: colors.text }]}>Recording voice… tap mic to send</Text>
          <Pressable
            onPress={() => void media.cancelVoiceRecording()}
            accessibilityRole="button"
            accessibilityLabel="Cancel voice recording"
          >
            <Text style={[styles.hint, { color: colors.textDim }]}>Cancel</Text>
          </Pressable>
        </View>
      ) : null}
      <View style={[styles.row, { borderTopColor: colors.border }]}>
        {onSendMedia ? (
          <>
            <Pressable
              onPress={() => void sendImage()}
              disabled={blocked}
              style={styles.iconBtn}
              accessibilityRole="button"
              accessibilityLabel="Attach image"
            >
              <AppIcon icon={feather('image')} size={18} color={blocked ? colors.textDim : colors.text} />
            </Pressable>
            <Pressable
              onPress={() => void toggleVoice()}
              disabled={disabled || busy}
              style={[
                styles.iconBtn,
                media.isRecordingVoice ? { backgroundColor: colors.border } : null,
              ]}
              accessibilityRole="button"
              accessibilityLabel={media.isRecordingVoice ? 'Send voice message' : 'Record voice message'}
            >
              <AppIcon
                icon={feather('mic')}
                size={18}
                color={media.isRecordingVoice ? colors.danger : blocked ? colors.textDim : colors.text}
              />
            </Pressable>
          </>
        ) : null}
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder="Message the customer"
          placeholderTextColor={colors.textDim}
          editable={!blocked}
          multiline
          style={[
            styles.input,
            {
              color: colors.text,
              backgroundColor: colors.input,
              borderColor: colors.border,
            },
          ]}
          accessibilityLabel="Message the customer"
        />
        <Pressable
          onPress={() => void submit()}
          disabled={!canSend}
          style={[
            styles.send,
            { backgroundColor: canSend ? colors.accent : colors.border },
          ]}
          accessibilityRole="button"
          accessibilityLabel="Send"
        >
          {busy ? (
            <ActivityIndicator color={colors.onAccent} />
          ) : (
            <AppIcon icon={feather('send')} size={16} color={colors.onAccent} />
          )}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  recordingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: spacing.xs,
  },
  hint: {
    fontFamily: fonts.body,
    fontSize: 12,
    marginBottom: 4,
  },
  iconBtn: {
    width: 36,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.md,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderRadius: radii.pill,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontFamily: fonts.body,
    fontSize: 16,
  },
  send: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
