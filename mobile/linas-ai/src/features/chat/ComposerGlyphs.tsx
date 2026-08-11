import { View } from 'react-native';

/** Shared + / mic / send touch target in the chat composer bar. */
export const COMPOSER_ACTION_SIZE = 36;

export function MicGlyph({ color, size = 20 }: { color: string; size?: number }) {
  const headW = size * 0.38;
  const headH = size * 0.52;
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <View
        style={{
          width: headW,
          height: headH,
          borderRadius: headW / 2,
          borderWidth: 2,
          borderColor: color,
          backgroundColor: 'transparent',
        }}
      />
      <View
        style={{
          position: 'absolute',
          bottom: size * 0.18,
          width: size * 0.55,
          height: size * 0.28,
          borderWidth: 2,
          borderTopWidth: 0,
          borderColor: color,
          borderBottomLeftRadius: size * 0.28,
          borderBottomRightRadius: size * 0.28,
        }}
      />
      <View
        style={{
          position: 'absolute',
          bottom: size * 0.08,
          width: 2,
          height: size * 0.14,
          backgroundColor: color,
          borderRadius: 1,
        }}
      />
      <View
        style={{
          position: 'absolute',
          bottom: size * 0.06,
          width: size * 0.28,
          height: 2,
          backgroundColor: color,
          borderRadius: 1,
        }}
      />
    </View>
  );
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
