import { Image, type ImageStyle } from 'react-native';

/** Canonical four-point Linas sparkle from assets/linas-app-icon.svg */
export const LINAS_SPARKLE_PATH =
  'M512 212 C532 385 577 430 750 450 C577 470 532 515 512 688 C492 515 447 470 274 450 C447 430 492 385 512 212Z';

/** Tight crop so the star fills its render box (full 1024 viewBox leaves ~54% padding). */
export const LINAS_SPARKLE_VIEWBOX = '274 212 476 476';

const SPARKLE_TEMPLATE = require('../../assets/linas-sparkle-template.png');

type Props = {
  size?: number;
  color: string;
};

/** Solid four-point sparkle — brand mark, not a 5-point star or Unicode glyph. */
export function LinasSparkleIcon({ size = 16, color }: Props) {
  const style: ImageStyle = {
    width: size,
    height: size,
    tintColor: color,
  };

  return (
    <Image
      source={SPARKLE_TEMPLATE}
      style={style}
      accessible={false}
      importantForAccessibility="no"
    />
  );
}
