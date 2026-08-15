import { Platform, TextInput, View, type TextStyle } from 'react-native';

import { ComposerExpandControl } from './ComposerExpandControl';
import { ComposerHeightProbe } from './ComposerHeightProbe';
import {
  COMPOSER_INPUT_MAX_H,
  COMPOSER_INPUT_PAD_H,
  COMPOSER_IOS_PAD_TOP,
} from './composerInputHeight';
import { composerStyles as styles } from './composerStyles';

type Props = {
  draft: string;
  placeholder: string;
  placeholderTextColor: string;
  textColor: string;
  inputHeight: number;
  fillHeight: boolean;
  stacked: boolean;
  atMaxHeight: boolean;
  showExpand: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  expandLabel: string;
  expandBg: string;
  expandIcon: string;
  assignInputRef: (node: TextInput | null) => void;
  onChangeText: (v: string) => void;
  onMeasuredLines: (lines: number) => void;
  onFocus: () => void;
  onBlur: () => void;
  textAlign: TextStyle['textAlign'];
  writingDirection: TextStyle['writingDirection'];
  editable: boolean;
  accessibilityLabel: string;
  slotWidth: number;
  onSlotWidth: (w: number) => void;
};

/** Draft field + wrap probe + optional expand control. */
export function ComposerDraftField({
  draft,
  placeholder,
  placeholderTextColor,
  textColor,
  inputHeight,
  fillHeight,
  stacked,
  atMaxHeight,
  showExpand,
  expanded,
  onToggleExpand,
  expandLabel,
  expandBg,
  expandIcon,
  assignInputRef,
  onChangeText,
  onMeasuredLines,
  onFocus,
  onBlur,
  textAlign,
  writingDirection,
  editable,
  accessibilityLabel,
  slotWidth,
  onSlotWidth,
}: Props) {
  return (
    <View
      style={[
        fillHeight ? styles.inputSlotExpanded : stacked ? styles.inputSlotStacked : styles.inputSlot,
        fillHeight ? null : { height: inputHeight, minHeight: inputHeight },
      ]}
      onLayout={(e) => {
        const w = Math.round(e.nativeEvent.layout.width);
        if (w > 0 && w !== slotWidth) onSlotWidth(w);
      }}
    >
      <ComposerHeightProbe
        draft={draft}
        width={Math.max(0, slotWidth - COMPOSER_INPUT_PAD_H * 2)}
        textAlign={textAlign}
        writingDirection={writingDirection}
        onMeasuredLines={onMeasuredLines}
      />
      <TextInput
        ref={assignInputRef}
        style={[
          styles.input,
          {
            color: textColor,
            minHeight: fillHeight ? undefined : inputHeight,
            height: fillHeight ? undefined : inputHeight,
            flex: fillHeight ? 1 : undefined,
            maxHeight: fillHeight ? undefined : COMPOSER_INPUT_MAX_H,
            textAlign,
            writingDirection,
            paddingTop: stacked ? (showExpand ? 6 : 2) : Platform.OS === 'ios' ? COMPOSER_IOS_PAD_TOP : 0,
            paddingRight: showExpand ? 36 : COMPOSER_INPUT_PAD_H,
          },
        ]}
        placeholder={placeholder}
        placeholderTextColor={placeholderTextColor}
        value={draft}
        onChangeText={onChangeText}
        onFocus={onFocus}
        onBlur={onBlur}
        multiline
        scrollEnabled={fillHeight || atMaxHeight}
        editable={editable}
        autoFocus={false}
        blurOnSubmit={false}
        textAlignVertical={stacked || fillHeight ? 'top' : 'center'}
        accessibilityLabel={accessibilityLabel}
      />
      {showExpand ? (
        <View style={styles.expandHitWrap} pointerEvents="box-none">
          <ComposerExpandControl
            expanded={expanded}
            onPress={onToggleExpand}
            backgroundColor={expandBg}
            iconColor={expandIcon}
            accessibilityLabel={expandLabel}
          />
        </View>
      ) : null}
    </View>
  );
}
