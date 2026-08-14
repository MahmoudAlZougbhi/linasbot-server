import { Image, View, type ImageStyle, type ImageURISource } from 'react-native';

import {
  SPARKLE_DARK_DEEP_URI,
  SPARKLE_DARK_URI,
  SPARKLE_LIGHT_DEEP_URI,
  SPARKLE_LIGHT_URI,
  SPARKLE_PNG_SIZE,
} from './linasSparklePng';

/** Canonical four-point Linas sparkle from assets/linas-app-icon.svg */
export const LINAS_SPARKLE_PATH =
  'M512 212 C532 385 577 430 750 450 C577 470 532 515 512 688 C492 515 447 470 274 450 C447 430 492 385 512 212Z';

/** Tight crop so the star fills its render box (full 1024 viewBox leaves ~54% padding). */
export const LINAS_SPARKLE_VIEWBOX = '274 212 476 476';

const SPARKLE_BY_COLOR: Record<string, string> = {
  '#178f87': SPARKLE_LIGHT_URI,
  '#008b8b': SPARKLE_LIGHT_URI,
  '#006d6d': SPARKLE_LIGHT_DEEP_URI,
  '#2dd4bf': SPARKLE_DARK_URI,
  '#5eead4': SPARKLE_DARK_DEEP_URI,
};

type Props = {
  size?: number;
  color: string;
};

function sparkleSource(color: string): ImageURISource {
  const uri = SPARKLE_BY_COLOR[color.toLowerCase()] ?? SPARKLE_LIGHT_URI;
  return { uri, width: SPARKLE_PNG_SIZE, height: SPARKLE_PNG_SIZE };
}

/** Solid four-point sparkle — brand mark, not a 5-point star or Unicode glyph. */
export function LinasSparkleIcon({ size = 16, color }: Props) {
  const style: ImageStyle = {
    width: size,
    height: size,
  };

  return (
    <View collapsable={false} pointerEvents="none" style={style}>
      <Image
        source={sparkleSource(color)}
        style={style}
        resizeMode="contain"
        fadeDuration={0}
        accessible={false}
        importantForAccessibility="no"
      />
    </View>
  );
}
