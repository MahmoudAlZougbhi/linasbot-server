import { useState } from 'react';
import {
  Pressable,
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
import { needsSeeAll, seeAllMaxHeight, SEE_ALL_LINE_HEIGHT } from './longTextClamp';
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

/** Editable Note/Description: 10 visible lines, then See all → full-screen copy. */
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

  return (
    <View>
      {label ? <Text style={[styles.label, labelStyle]}>{label}</Text> : null}
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={placeholderTextColor ?? '#8A9A98'}
        multiline
        textAlignVertical="top"
        scrollEnabled={showSeeAll}
        onContentSizeChange={(e) => setContentH(e.nativeEvent.contentSize.height)}
        style={[styles.input, { maxHeight: maxH, lineHeight: SEE_ALL_LINE_HEIGHT }, inputStyle]}
      />
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
  input: {
    backgroundColor: '#F3F8F7',
    borderWidth: 1,
    borderColor: '#D7E5E3',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: '#10221A',
    fontFamily: fonts.body,
    fontSize: 16,
    marginBottom: 8,
  },
  seeAll: { alignSelf: 'flex-start', paddingVertical: 4, marginBottom: 6 },
  seeAllText: { color: AI_SETUP_TEAL, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
  hint: { color: '#8A9A98', fontFamily: fonts.body, fontSize: 12, lineHeight: 18, marginBottom: 8 },
});
