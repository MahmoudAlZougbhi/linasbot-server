import * as Clipboard from 'expo-clipboard';
import { useEffect, useRef, useState } from 'react';
import { Animated, Pressable, StyleSheet, View } from 'react-native';

import { AppIcon, feather, type AppIconName } from '../../components/AppIcon';
import { useTheme } from '../../theme';

type Props = {
  text: string;
  onRetry?: () => void;
  /** Pack copy/retry toward the AI message's script edge. */
  edgeRtl?: boolean;
};

type ActionIconProps = {
  accessibilityLabel: string;
  icon: AppIconName;
  color: string;
  onPress: () => void;
};

function ActionIconButton({ accessibilityLabel, icon, color, onPress }: ActionIconProps) {
  const scale = useRef(new Animated.Value(1)).current;
  const opacity = useRef(new Animated.Value(1)).current;

  function animateTo(nextScale: number, nextOpacity: number, duration: number) {
    Animated.parallel([
      Animated.timing(scale, { toValue: nextScale, duration, useNativeDriver: true }),
      Animated.timing(opacity, { toValue: nextOpacity, duration, useNativeDriver: true }),
    ]).start();
  }

  return (
    <Pressable
      onPress={onPress}
      onPressIn={() => animateTo(0.88, 0.55, 90)}
      onPressOut={() => animateTo(1, 1, 140)}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      hitSlop={10}
    >
      <Animated.View style={[styles.iconWrap, { opacity, transform: [{ scale }] }]}>
        <AppIcon icon={icon} size={16} color={color} />
      </Animated.View>
    </Pressable>
  );
}

export function MessageActions({ text, onRetry, edgeRtl = false }: Props) {
  const { colors } = useTheme();
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    };
  }, []);

  async function onCopy() {
    const body = text?.trim();
    if (!body) return;
    await Clipboard.setStringAsync(body);
    setCopied(true);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), 900);
  }

  return (
    <View style={[styles.row, edgeRtl ? styles.rowRtl : styles.rowLtr]}>
      <ActionIconButton
        accessibilityLabel={copied ? 'Copied' : 'Copy message'}
        icon={feather(copied ? 'check' : 'copy')}
        color={copied ? colors.accent : colors.textMuted}
        onPress={() => void onCopy()}
      />
      {onRetry ? (
        <ActionIconButton
          accessibilityLabel="Retry"
          icon={feather('refresh-cw')}
          color={colors.textMuted}
          onPress={onRetry}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 6 },
  rowLtr: { marginLeft: 2 },
  rowRtl: { marginRight: 2, flexDirection: 'row-reverse' },
  iconWrap: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
