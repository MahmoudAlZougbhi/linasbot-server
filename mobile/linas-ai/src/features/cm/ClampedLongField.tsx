import { useEffect, useRef, useState } from 'react';
import {
  Keyboard,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextStyle,
} from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts } from '../../theme';
import { AI_SETUP_TEAL } from './aiSetupDesign';
import { needsSeeAll, NOTE_TEXT_COLOR, seeAllMaxHeight, SEE_ALL_LINE_HEIGHT } from './longTextClamp';
import { SeeAllTextModal } from './SeeAllTextModal';

type Props = {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
  countLabel?: string;
  placeholderTextColor?: string;
  labelStyle?: StyleProp<TextStyle>;
  inputStyle?: StyleProp<TextStyle>;
  hintStyle?: StyleProp<TextStyle>;
};

/** Note/Description: tap to edit. Scroll never focuses. See all is read-only. */
export function ClampedLongField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  countLabel,
  placeholderTextColor,
  labelStyle,
  inputStyle,
  hintStyle,
}: Props) {
  const { tr } = useI18n();
  const inputRef = useRef<TextInput>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [contentH, setContentH] = useState(0);
  const showSeeAll = needsSeeAll(value, contentH);
  const maxH = seeAllMaxHeight(12);
  const placeholderColor = placeholderTextColor ?? '#8A9A98';
  const countPad = countLabel ? styles.countPad : null;
  const canEdit = !open;

  useEffect(() => {
    if (!open) return;
    setEditing(false);
    Keyboard.dismiss();
  }, [open]);

  useEffect(() => {
    if (editing && canEdit) inputRef.current?.focus();
  }, [editing, canEdit]);

  function startEdit() {
    if (!canEdit) return;
    setEditing(true);
  }

  function openSeeAll() {
    setEditing(false);
    Keyboard.dismiss();
    setOpen(true);
  }

  return (
    <View>
      {label ? <Text style={[styles.label, labelStyle]}>{label}</Text> : null}
      <View style={[styles.box, showSeeAll && !editing ? { maxHeight: maxH } : null]}>
        {editing && canEdit ? (
          <TextInput
            ref={inputRef}
            value={value}
            onChangeText={onChange}
            placeholder={placeholder}
            placeholderTextColor={placeholderColor}
            multiline
            textAlignVertical="top"
            scrollEnabled={false}
            showSoftInputOnFocus
            autoFocus
            onBlur={() => setEditing(false)}
            onContentSizeChange={(e) => setContentH(e.nativeEvent.contentSize.height)}
            style={[styles.shortInput, countPad, inputStyle, { color: NOTE_TEXT_COLOR }]}
          />
        ) : showSeeAll ? (
          <ScrollView
            style={styles.boxFill}
            contentContainerStyle={[styles.previewBody, countPad]}
            scrollEnabled
            keyboardShouldPersistTaps="never"
            nestedScrollEnabled
            keyboardDismissMode="on-drag"
            showsVerticalScrollIndicator={false}
            onContentSizeChange={(_, height) => setContentH(height)}
          >
            <Pressable onPress={startEdit} accessibilityRole="button">
              <Text style={styles.previewText}>{value}</Text>
            </Pressable>
          </ScrollView>
        ) : (
          <Pressable onPress={startEdit} accessibilityRole="button">
            <Text
              style={[
                styles.shortInput,
                countPad,
                inputStyle,
                { color: value ? NOTE_TEXT_COLOR : placeholderColor },
              ]}
            >
              {value || placeholder || ' '}
            </Text>
          </Pressable>
        )}
        {countLabel ? (
          <Text pointerEvents="none" style={styles.count}>
            {countLabel}
          </Text>
        ) : null}
      </View>
      {showSeeAll ? (
        <Pressable
          onPress={openSeeAll}
          accessibilityRole="button"
          accessibilityLabel={tr('aiSetupSeeAll')}
          style={styles.seeAll}
        >
          <Text style={styles.seeAllText}>{tr('aiSetupSeeAll')}</Text>
        </Pressable>
      ) : null}
      {hint ? <Text style={[styles.hint, hintStyle]}>{hint}</Text> : null}
      <SeeAllTextModal
        visible={open}
        title={label || tr('aiSetupSeeAll')}
        text={value}
        countLabel={countLabel}
        onClose={() => setOpen(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  label: {
    color: '#5B6B6A',
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    marginBottom: 6,
  },
  box: {
    backgroundColor: '#F3F8F7',
    borderWidth: 1,
    borderColor: '#D7E5E3',
    borderRadius: 10,
    marginBottom: 8,
    overflow: 'hidden',
  },
  boxFill: { flexGrow: 0 },
  previewBody: { paddingHorizontal: 14, paddingVertical: 12 },
  countPad: { paddingBottom: 28 },
  count: {
    position: 'absolute',
    bottom: 8,
    right: 12,
    color: '#8A9A98',
    fontFamily: fonts.body,
    fontSize: 12,
  },
  previewText: {
    color: NOTE_TEXT_COLOR,
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: SEE_ALL_LINE_HEIGHT,
  },
  shortInput: {
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: SEE_ALL_LINE_HEIGHT,
    color: NOTE_TEXT_COLOR,
  },
  seeAll: { alignSelf: 'flex-start', paddingVertical: 4, marginBottom: 6 },
  seeAllText: { color: AI_SETUP_TEAL, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
  hint: { color: '#8A9A98', fontFamily: fonts.body, fontSize: 12, lineHeight: 18, marginBottom: 8 },
});
