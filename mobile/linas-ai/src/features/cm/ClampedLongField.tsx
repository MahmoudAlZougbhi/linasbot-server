import { useState } from 'react';
import {
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
  placeholderTextColor?: string;
  labelStyle?: StyleProp<TextStyle>;
  inputStyle?: StyleProp<TextStyle>;
  hintStyle?: StyleProp<TextStyle>;
};

/** Note/Description: 10-line preview (no keyboard). See all is the editor. */
export function ClampedLongField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  placeholderTextColor,
  labelStyle,
  inputStyle,
  hintStyle,
}: Props) {
  const { tr } = useI18n();
  const [open, setOpen] = useState(false);
  const [contentH, setContentH] = useState(0);
  const showSeeAll = needsSeeAll(value, contentH);
  const maxH = seeAllMaxHeight(12);
  const placeholderColor = placeholderTextColor ?? '#8A9A98';

  return (
    <View>
      {label ? <Text style={[styles.label, labelStyle]}>{label}</Text> : null}
      {showSeeAll ? (
        <ScrollView
          style={[styles.box, { maxHeight: maxH }]}
          contentContainerStyle={styles.previewBody}
          scrollEnabled
          keyboardShouldPersistTaps="never"
          nestedScrollEnabled
          onContentSizeChange={(_, height) => setContentH(height)}
        >
          <Text style={styles.previewText} pointerEvents="none">
            {value}
          </Text>
        </ScrollView>
      ) : (
        <TextInput
          value={value}
          onChangeText={onChange}
          placeholder={placeholder}
          placeholderTextColor={placeholderColor}
          multiline
          textAlignVertical="top"
          scrollEnabled={false}
          showSoftInputOnFocus
          onContentSizeChange={(e) => setContentH(e.nativeEvent.contentSize.height)}
          style={[styles.box, styles.shortInput, inputStyle, { color: NOTE_TEXT_COLOR }]}
        />
      )}
      {showSeeAll ? (
        <Pressable
          onPress={() => setOpen(true)}
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
        onChange={onChange}
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
  },
  previewBody: { paddingHorizontal: 14, paddingVertical: 12 },
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
