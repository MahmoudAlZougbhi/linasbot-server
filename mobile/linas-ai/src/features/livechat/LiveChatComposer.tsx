import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { fonts, radii, spacing, useTheme } from '../../theme';

type Props = {
  onSend: (text: string) => Promise<boolean>;
  busy: boolean;
  disabled?: boolean;
};

export function LiveChatComposer({ onSend, busy, disabled }: Props) {
  const { colors } = useTheme();
  const [draft, setDraft] = useState('');
  const canSend = !disabled && !busy && draft.trim().length > 0;

  const submit = async () => {
    const text = draft.trim();
    if (!text || busy || disabled) return;
    const ok = await onSend(text);
    if (ok) setDraft('');
  };

  return (
    <View style={[styles.row, { borderTopColor: colors.border }]}>
      <TextInput
        value={draft}
        onChangeText={setDraft}
        placeholder="Message the customer"
        placeholderTextColor={colors.textDim}
        editable={!disabled && !busy}
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
