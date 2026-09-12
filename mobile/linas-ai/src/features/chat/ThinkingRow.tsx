import { StyleSheet, View } from 'react-native';

import { LinasStarMark } from '../../components/LinasStarMark';
import {
  aiMessageColStyle,
  aiMessageHeaderStyle,
  aiMessageRowStyle,
  isRtlText,
} from '../../lib/textDirection';
import { spacing, useTheme } from '../../theme';
import { TYPING_DOT_COLOR, TypingDots } from './TypingDots';

type Props = {
  label: string;
};

/**
 * Live-turn placeholder: landing Here typing bubble (white, 3 bouncing dots).
 * Replaced by streamed liveText in the same footer when deltas start.
 */
export function ThinkingRow({ label }: Props) {
  const { colors, resolved } = useTheme();
  const rtl = isRtlText(label);
  const corner = 18;
  const tail = 6;
  const dotColor = resolved === 'dark' ? colors.accent : TYPING_DOT_COLOR;

  return (
    <View
      style={[styles.row, styles.rowAi, aiMessageRowStyle(label)]}
      accessibilityLiveRegion="polite"
      accessibilityRole="text"
      accessibilityLabel={label}
    >
      <View style={[styles.col, styles.colAi]}>
        <View style={[styles.aiLabelRow, aiMessageHeaderStyle]}>
          <LinasStarMark
            size={16}
            labelSize={13}
            labeled
            label="Linas"
            labelColor={colors.text}
          />
        </View>
        <View style={[styles.bodyCol, aiMessageColStyle(label)]}>
          <View
            style={[
              styles.bubble,
              {
                backgroundColor: colors.bubbleAi,
                borderColor: colors.borderSoft,
                borderTopLeftRadius: corner,
                borderTopRightRadius: corner,
                borderBottomLeftRadius: rtl ? corner : tail,
                borderBottomRightRadius: rtl ? tail : corner,
                shadowOpacity: resolved === 'dark' ? 0 : 0.06,
                elevation: resolved === 'dark' ? 0 : 2,
              },
            ]}
          >
            <TypingDots color={dotColor} />
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    marginBottom: spacing.md,
  },
  rowAi: { alignSelf: 'flex-start', maxWidth: '88%' },
  col: { flexShrink: 1 },
  colAi: { width: '100%' },
  aiLabelRow: {
    alignSelf: 'flex-start',
    paddingTop: 4,
    paddingBottom: 2,
    marginBottom: 4,
    overflow: 'visible',
  },
  bodyCol: {
    width: '100%',
    alignSelf: 'stretch',
  },
  bubble: {
    alignSelf: 'flex-start',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
    shadowColor: '#171A19',
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 8,
  },
});
