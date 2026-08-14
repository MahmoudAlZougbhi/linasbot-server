import { StyleSheet, View } from 'react-native';

import { AppIcon, feather, ion } from '../../components/AppIcon';

/** Shared + / mic / send touch target in the chat composer bar. */
export const COMPOSER_ACTION_SIZE = 36;
export const COMPOSER_SEND_SIZE = 36;
export const COMPOSER_PLUS_DISK = 32;
const PLUS_STROKE = 1.75;
const PLUS_ARM = 13;

/** Thin plus on a light-gray disk — matches the screenshot composer, not a font “+”. */
export function PlusCircleGlyph({
  color,
  backgroundColor,
  borderColor,
  size = COMPOSER_PLUS_DISK,
}: {
  color: string;
  backgroundColor: string;
  borderColor: string;
  size?: number;
}) {
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <View
        style={{
          position: 'absolute',
          width: PLUS_ARM,
          height: PLUS_STROKE,
          borderRadius: 1,
          backgroundColor: color,
        }}
      />
      <View
        style={{
          position: 'absolute',
          width: PLUS_STROKE,
          height: PLUS_ARM,
          borderRadius: 1,
          backgroundColor: color,
        }}
      />
    </View>
  );
}

export function SendArrowGlyph({ color, size = 18 }: { color: string; size?: number }) {
  return <AppIcon icon={ion('arrow-up')} size={size} color={color} />;
}

export function MicGlyph({ color, size = 20 }: { color: string; size?: number }) {
  return <AppIcon icon={feather('mic')} size={size} color={color} />;
}

export function StopGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 12, height: 12, borderRadius: 2.5, backgroundColor: color }} />
  );
}

export function CheckGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 16, height: 16, alignItems: 'center', justifyContent: 'center' }}>
      <View
        style={{
          width: 9,
          height: 5,
          borderLeftWidth: 2,
          borderBottomWidth: 2,
          borderColor: color,
          transform: [{ rotate: '-45deg' }, { translateY: -1 }],
        }}
      />
    </View>
  );
}

export function DiscardGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 16, height: 16, alignItems: 'center', justifyContent: 'center' }}>
      <View
        style={{
          position: 'absolute',
          width: 12,
          height: 2,
          backgroundColor: color,
          borderRadius: 1,
          transform: [{ rotate: '45deg' }],
        }}
      />
      <View
        style={{
          position: 'absolute',
          width: 12,
          height: 2,
          backgroundColor: color,
          borderRadius: 1,
          transform: [{ rotate: '-45deg' }],
        }}
      />
    </View>
  );
}

export function formatVoiceElapsed(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}
