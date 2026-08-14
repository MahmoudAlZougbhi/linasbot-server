import { useEffect, useRef, useState, type RefObject } from 'react';
import {
  ActivityIndicator,
  Animated,
  Keyboard,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { textDirectionStyle } from '../../lib/textDirection';
import { useI18n } from '../../i18n/LanguageContext';
import { useTheme } from '../../theme';
import { ComposerEditChip } from './ComposerEditChip';
import {
  PlusCircleGlyph,
  SendArrowGlyph,
  StopGlyph,
} from './ComposerGlyphs';
import { ComposerDraftField } from './ComposerDraftField';
import { ComposerModelChip } from './ComposerModelChip';
import { composerStyles as styles } from './composerStyles';
import { LinEffortSheet } from './LinEffortSheet';
import type { OwnerChatMode } from './ownerChatMode';
import { useComposerInputAutoGrow } from './useComposerInputAutoGrow';
import type { VoiceState } from './useVoiceDraft';
import { VoiceComposerControls } from './VoiceComposerControls';

type Props = {
  draft: string;
  onChangeDraft: (v: string) => void;
  onSend: () => void;
  onPlus?: () => void;
  onToggleVoice?: () => void;
  onResumeVoice?: () => void;
  onConfirmVoice?: () => void;
  onDiscardVoice?: () => void;
  onStop?: () => void;
  sending: boolean;
  canSendWithAttachment?: boolean;
  voiceState?: VoiceState;
  elapsedMs?: number;
  metering?: number | null;
  inputRef?: RefObject<TextInput | null>;
  showPlus?: boolean;
  showMic?: boolean;
  showDisclaimer?: boolean;
  autoFocus?: boolean;
  ownerMode?: OwnerChatMode;
  onOwnerModeChange?: (mode: OwnerChatMode) => void;
  showModelChip?: boolean;
  editChipActive?: boolean;
  onClearEditChip?: () => void;
};

/**
 * Compact idle pill; focused/growing stacks text on top and pins + / mic / send below.
 */
export function ChatComposer({
  draft,
  onChangeDraft,
  onSend,
  onPlus,
  onToggleVoice,
  onResumeVoice,
  onConfirmVoice,
  onDiscardVoice,
  onStop,
  sending,
  canSendWithAttachment = false,
  voiceState = 'idle',
  elapsedMs = 0,
  metering: _metering,
  inputRef,
  showPlus = false,
  showMic = false,
  showDisclaimer = true,
  autoFocus = false,
  ownerMode = 'chat',
  onOwnerModeChange,
  showModelChip = false,
  editChipActive = false,
  onClearEditChip,
}: Props) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { tr, isRtl } = useI18n();
  const [effortOpen, setEffortOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [slotWidth, setSlotWidth] = useState(0);
  const pulse = useRef(new Animated.Value(1)).current;
  const ring = useRef(new Animated.Value(0.55)).current;
  const suppressFocusRef = useRef(false);
  const {
    inputHeight,
    atMaxHeight,
    showExpandControl,
    localInputRef,
    assignInputRef,
    handleChangeText,
    handleMeasuredLines,
    scrollComposerToEnd,
  } = useComposerInputAutoGrow(draft, inputRef);
  const recording = voiceState === 'recording';
  const paused = voiceState === 'paused';
  const transcribing = voiceState === 'transcribing';
  const voiceBusy = recording || paused || transcribing;
  const canSend = Boolean(draft.trim() || canSendWithAttachment);
  const streamingStop = Boolean(onStop && sending);
  const showVoiceControl = Boolean(showMic && onToggleVoice && !streamingStop);
  const chipTappable = Boolean(showModelChip && onOwnerModeChange);
  const draftDir = textDirectionStyle(draft);
  const draftEmpty = !draft.trim();
  const stacked = expanded || focused || !draftEmpty || voiceBusy;
  const showExpand = expanded || showExpandControl;
  const idleAlign = isRtl ? 'right' : 'left';
  const idleWriting = isRtl ? 'rtl' : 'ltr';
  const inputTextAlign = draftEmpty ? idleAlign : draftDir.textAlign;

  function dismissKeyboard() {
    localInputRef.current?.blur();
    Keyboard.dismiss();
  }

  useEffect(() => {
    if (!recording) {
      pulse.setValue(1);
      ring.setValue(0.55);
      return;
    }
    const scaleLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1.06, duration: 480, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 480, useNativeDriver: true }),
      ]),
    );
    const ringLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(ring, { toValue: 1, duration: 700, useNativeDriver: true }),
        Animated.timing(ring, { toValue: 0.4, duration: 700, useNativeDriver: true }),
      ]),
    );
    scaleLoop.start();
    ringLoop.start();
    return () => {
      scaleLoop.stop();
      ringLoop.stop();
    };
  }, [recording, pulse, ring]);

  useEffect(() => {
    if (draft.length === 0 && expanded) setExpanded(false);
  }, [draft, expanded]);

  function toggleExpand() {
    if (expanded) {
      setExpanded(false);
      requestAnimationFrame(scrollComposerToEnd);
      return;
    }
    setExpanded(true);
    requestAnimationFrame(() => localInputRef.current?.focus());
  }

  useEffect(() => {
    if (!autoFocus || suppressFocusRef.current) return;
    const t = setTimeout(() => {
      if (suppressFocusRef.current) return;
      localInputRef.current?.focus();
    }, 120);
    return () => clearTimeout(t);
  }, [autoFocus]);

  useEffect(() => {
    const showEvt = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvt = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const show = Keyboard.addListener(showEvt, () => setKeyboardOpen(true));
    const hide = Keyboard.addListener(hideEvt, () => setKeyboardOpen(false));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);

  function handleSend() {
    if (sending || !canSend || voiceBusy) return;
    suppressFocusRef.current = true;
    dismissKeyboard();
    onSend();
    requestAnimationFrame(dismissKeyboard);
    setTimeout(dismissKeyboard, 80);
  }

  const idlePlaceholder =
    ownerMode === 'work' ? tr('composerPlaceholderWork') : tr('composerPlaceholderChat');
  const placeholder = recording
    ? tr('composerListening')
    : paused
      ? tr('composerPaused')
      : transcribing
        ? tr('composerTranscribing')
        : idlePlaceholder;

  const sendBtn = streamingStop ? (
    <Pressable
      style={[styles.sendInside, { backgroundColor: colors.accent }]}
      onPress={onStop}
      accessibilityLabel={tr('composerStop')}
    >
      <StopGlyph color={colors.onAccent} />
    </Pressable>
  ) : (
    <Pressable
      style={[
        styles.sendInside,
        { backgroundColor: colors.accent },
        sending && styles.sendBusy,
      ]}
      onPress={handleSend}
      disabled={sending || !canSend || voiceBusy}
      accessibilityLabel={tr('composerSend')}
    >
      {sending ? (
        <ActivityIndicator color={colors.onAccent} size="small" />
      ) : (
        <SendArrowGlyph color={colors.onAccent} size={18} />
      )}
    </Pressable>
  );

  const plusBtn =
    showPlus && onPlus ? (
      <Pressable
        style={styles.iconHit}
        onPress={onPlus}
        accessibilityLabel={tr('composerMoreActions')}
        hitSlop={6}
      >
        <PlusCircleGlyph
          color={colors.text}
          backgroundColor={colors.featuredIconBg}
          borderColor={colors.featuredIconBorder}
        />
      </Pressable>
    ) : stacked ? (
      <View style={styles.iconHit} />
    ) : null;

  const trailing = (
    <>
      {showVoiceControl ? (
        <VoiceComposerControls
          voiceState={voiceState}
          elapsedMs={elapsedMs}
          pulse={pulse}
          ring={ring}
          onToggleVoice={onToggleVoice}
          onResumeVoice={onResumeVoice}
          onConfirmVoice={onConfirmVoice}
          onDiscardVoice={onDiscardVoice}
          onBeforeStart={dismissKeyboard}
        />
      ) : null}
      {sendBtn}
    </>
  );

  return (
    <View
      style={[
        expanded ? styles.expandOverlay : styles.wrap,
        {
          paddingTop: expanded ? insets.top + 8 : undefined,
          paddingBottom: keyboardOpen ? 8 : Math.max(insets.bottom, 10),
          backgroundColor: expanded ? colors.overlay : colors.bg,
        },
      ]}
    >
      {expanded ? null : (
        <ComposerEditChip active={Boolean(editChipActive)} onClear={onClearEditChip} />
      )}

      {showModelChip && !expanded ? (
        <ComposerModelChip
          mode={ownerMode}
          tappable={chipTappable}
          open={effortOpen}
          onOpen={() => {
            dismissKeyboard();
            setEffortOpen(true);
          }}
        />
      ) : null}

      <View
        style={[
          expanded ? styles.expandSheet : styles.pill,
          expanded ? null : stacked ? styles.pillStacked : styles.pillCompact,
          {
            backgroundColor: colors.surface,
            shadowColor: colors.text,
          },
        ]}
      >
        {!stacked && plusBtn}
        <ComposerDraftField
          draft={draft}
          placeholder={placeholder}
          placeholderTextColor={colors.textDim}
          textColor={colors.text}
          inputHeight={inputHeight}
          fillHeight={expanded}
          stacked={stacked}
          atMaxHeight={atMaxHeight}
          showExpand={showExpand}
          expanded={expanded}
          onToggleExpand={toggleExpand}
          expandLabel={expanded ? tr('composerCollapse') : tr('composerExpand')}
          expandBg={colors.featuredIconBg}
          expandIcon={colors.textMuted}
          assignInputRef={assignInputRef}
          onChangeText={(v) => handleChangeText(v, onChangeDraft)}
          onMeasuredLines={handleMeasuredLines}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          textAlign={inputTextAlign}
          writingDirection={draftEmpty ? idleWriting : draftDir.writingDirection}
          editable={!voiceBusy}
          accessibilityLabel={idlePlaceholder}
          slotWidth={slotWidth}
          onSlotWidth={setSlotWidth}
        />
        {stacked ? (
          <View style={styles.actionRow}>
            {plusBtn}
            <View style={styles.actionRight}>{trailing}</View>
          </View>
        ) : (
          trailing
        )}
      </View>

      {showDisclaimer && !expanded ? (
        <Text style={[styles.disclaimer, { color: colors.textDim }]}>
          {tr('composerDisclaimer')}
        </Text>
      ) : null}

      {chipTappable ? (
        <LinEffortSheet
          open={effortOpen}
          mode={ownerMode}
          onClose={() => setEffortOpen(false)}
          onSelect={onOwnerModeChange!}
        />
      ) : null}
    </View>
  );
}
