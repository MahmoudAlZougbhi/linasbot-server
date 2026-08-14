import { Text, type TextStyle } from 'react-native';

import { fonts } from '../../theme';
import {
  COMPOSER_INPUT_LINE_HEIGHT,
  COMPOSER_MIN_PROBE_WIDTH,
} from './composerInputHeight';

type Props = {
  draft: string;
  width: number;
  textAlign: TextStyle['textAlign'];
  writingDirection: TextStyle['writingDirection'];
  onMeasuredLines: (lines: number) => void;
};

const probeStyle: TextStyle = {
  position: 'absolute',
  opacity: 0,
  left: 0,
  top: 0,
  zIndex: -1,
  fontFamily: fonts.body,
  fontSize: 16,
  lineHeight: COMPOSER_INPUT_LINE_HEIGHT,
  paddingHorizontal: 0,
  paddingVertical: 0,
  includeFontPadding: false,
};

/**
 * Hidden Text with the same type metrics as the composer field.
 * Reports wrap buckets only. iOS contentSize is not used for height.
 */
export function ComposerHeightProbe({
  draft,
  width,
  textAlign,
  writingDirection,
  onMeasuredLines,
}: Props) {
  if (width < COMPOSER_MIN_PROBE_WIDTH) return null;
  const body = draft.endsWith('\n') ? `${draft}\u200b` : draft || ' ';
  return (
    <Text
      accessible={false}
      pointerEvents="none"
      onTextLayout={(e) => {
        onMeasuredLines(Math.max(1, e.nativeEvent.lines.length));
      }}
      style={[probeStyle, { width, textAlign, writingDirection }]}
    >
      {body}
    </Text>
  );
}
