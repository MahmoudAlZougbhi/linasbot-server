import { useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { AppModal } from '../../components/AppModal';
import { ModalScrim } from '../../components/ModalScrim';

import { PrimaryButton } from '../../components/PrimaryButton';
import { TextField } from '../../components/TextField';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing, typography } from '../../theme';

type Props = {
  visible: boolean;
  initialQuestion: string;
  initialAnswer: string;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (question: string, answer: string) => void;
};

export function LikeFeedbackModal({
  visible,
  initialQuestion,
  initialAnswer,
  busy,
  error,
  onClose,
  onSubmit,
}: Props) {
  const { tr } = useI18n();
  const [question, setQuestion] = useState(initialQuestion);
  const [answer, setAnswer] = useState(initialAnswer);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    setQuestion(initialQuestion);
    setAnswer(initialAnswer);
    setLocalError(null);
  }, [visible, initialQuestion, initialAnswer]);

  const handleSave = () => {
    const q = question.trim();
    const a = answer.trim();
    if (!q || !a) {
      setLocalError(tr('likeFaqNeedBoth'));
      return;
    }
    setLocalError(null);
    onSubmit(q, a);
  };

  return (
    <AppModal visible={visible} animationType="fade" onRequestClose={busy ? undefined : onClose}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ModalScrim onPress={busy ? undefined : onClose} justify="center" style={styles.backdrop}>
          <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
            <ScrollView keyboardShouldPersistTaps="handled" bounces={false}>
              <Text style={styles.title}>{tr('likeFaqTitle')}</Text>
              <Text style={styles.hint}>{tr('likeFaqHint')}</Text>

              <Text style={styles.label}>{tr('likeFaqQuestion')}</Text>
              <TextField
                value={question}
                onChangeText={setQuestion}
                multiline
                editable={!busy}
                placeholder={tr('likeFaqQuestionPlaceholder')}
                style={styles.field}
              />

              <Text style={styles.label}>{tr('likeFaqAnswer')}</Text>
              <TextField
                value={answer}
                onChangeText={setAnswer}
                multiline
                editable={!busy}
                placeholder={tr('likeFaqAnswerPlaceholder')}
                style={styles.fieldAnswer}
              />

              {localError || error ? (
                <Text style={styles.error}>{localError || error}</Text>
              ) : null}

              <View style={styles.actions}>
                <PrimaryButton
                  label={tr('likeFaqSave')}
                  onPress={handleSave}
                  loading={busy}
                  disabled={busy}
                  style={styles.actionFlex}
                />
                <PrimaryButton
                  label={tr('usersCancel')}
                  onPress={onClose}
                  variant="ghost"
                  disabled={busy}
                  style={styles.actionFlex}
                />
              </View>
            </ScrollView>
          </Pressable>
        </ModalScrim>
      </KeyboardAvoidingView>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  backdrop: {
    padding: spacing.lg,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.xl,
    padding: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
    maxHeight: '90%',
  },
  title: {
    ...typography.title,
    color: colors.accentDeep,
    fontSize: 20,
    marginBottom: spacing.sm,
  },
  hint: {
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 13,
    lineHeight: 18,
    marginBottom: spacing.lg,
  },
  label: {
    color: colors.text,
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    marginBottom: 6,
  },
  field: { minHeight: 72, marginBottom: spacing.md },
  fieldAnswer: { minHeight: 96, marginBottom: spacing.md },
  error: {
    color: colors.danger,
    fontFamily: fonts.body,
    fontSize: 13,
    marginBottom: spacing.md,
  },
  actions: { flexDirection: 'row', gap: 10, marginTop: spacing.sm },
  actionFlex: { flex: 1 },
});
