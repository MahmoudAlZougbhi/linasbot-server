import { StyleSheet, View } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';

const GRADIENT_ID = 'drawerFadeLine';

type Props = {
  lineColor: string;
  starColor: string;
};

/** Horizontal rule that fades toward the edges with a centered Linas sparkle. */
export function DrawerFadeSeparator({ lineColor, starColor }: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.lineTrack} pointerEvents="none">
        <Svg width="100%" height={1} preserveAspectRatio="none">
          <Defs>
            <LinearGradient id={GRADIENT_ID} x1="0" y1="0" x2="1" y2="0">
              <Stop offset="0" stopColor={lineColor} stopOpacity={0} />
              <Stop offset="0.18" stopColor={lineColor} stopOpacity={0.4} />
              <Stop offset="0.5" stopColor={lineColor} stopOpacity={0.9} />
              <Stop offset="0.82" stopColor={lineColor} stopOpacity={0.4} />
              <Stop offset="1" stopColor={lineColor} stopOpacity={0} />
            </LinearGradient>
          </Defs>
          <Rect x="0" y="0" width="100%" height="1" fill={`url(#${GRADIENT_ID})`} />
        </Svg>
      </View>
      <LinasSparkleIcon size={10} color={starColor} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    height: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  lineTrack: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
  },
});
