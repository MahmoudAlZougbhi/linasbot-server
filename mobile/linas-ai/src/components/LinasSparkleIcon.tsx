import Svg, { Path } from 'react-native-svg';

/** Canonical four-point Linas sparkle from assets/linas-app-icon.svg */
export const LINAS_SPARKLE_PATH =
  'M512 212 C532 385 577 430 750 450 C577 470 532 515 512 688 C492 515 447 470 274 450 C447 430 492 385 512 212Z';

const VIEWBOX = 1024;

type Props = {
  size?: number;
  color: string;
};

/** Solid four-point sparkle — brand mark, not a 5-point star or Unicode glyph. */
export function LinasSparkleIcon({ size = 16, color }: Props) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`}
      accessible={false}
      importantForAccessibility="no"
    >
      <Path d={LINAS_SPARKLE_PATH} fill={color} />
    </Svg>
  );
}
