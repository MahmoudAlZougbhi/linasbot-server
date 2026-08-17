import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { colors, fonts, spacing } from '../../theme';
import {
  IntegrationPlatformIcon,
  type IntegrationPlatform,
} from './IntegrationPlatformIcon';

type Props = {
  platform: IntegrationPlatform;
  title: string;
  subtitle: string;
  connected: boolean;
  soon?: boolean;
  busy?: boolean;
  connectLabel: string;
  connectedLabel: string;
  notConnectedLabel: string;
  comingSoonLabel: string;
  statusLabel?: string;
  healthLabel?: string;
  menuLabel: string;
  showConnect: boolean;
  showMenu: boolean;
  showHealth: boolean;
  onConnect?: () => void;
  onMenu?: () => void;
  children?: ReactNode;
};

/** White shadowed Integrations card chrome (list + WhatsApp). */
export function IntegrationCardShell({
  platform,
  title,
  subtitle,
  connected,
  soon,
  busy,
  connectLabel,
  connectedLabel,
  notConnectedLabel,
  comingSoonLabel,
  statusLabel,
  healthLabel,
  menuLabel,
  showConnect,
  showMenu,
  showHealth,
  onConnect,
  onMenu,
  children,
}: Props) {
  const pillLabel = soon
    ? comingSoonLabel
    : statusLabel || (connected ? connectedLabel : notConnectedLabel);
  const pillConnected = !soon && connected && !statusLabel;

  return (
    <View style={styles.card}>
      <View style={[styles.head, showConnect ? styles.headCenter : styles.headTop]}>
        <IntegrationPlatformIcon platform={platform} size={48} />
        <View style={styles.meta}>
          <Text style={styles.title}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
          <View style={[styles.pill, pillConnected ? styles.pillOn : styles.pillOff]}>
            <Text style={[styles.pillText, pillConnected ? styles.pillTextOn : styles.pillTextOff]}>
              {pillLabel}
            </Text>
          </View>
        </View>
        {showMenu ? (
          <Pressable
            onPress={onMenu}
            accessibilityRole="button"
            accessibilityLabel={menuLabel}
            hitSlop={8}
            style={({ pressed }) => [styles.menuBtn, pressed && styles.pressed]}
          >
            <AppIcon icon={feather('more-horizontal')} size={20} color={colors.textMuted} />
          </Pressable>
        ) : null}
        {showConnect ? (
          <Pressable
            onPress={onConnect}
            disabled={busy}
            accessibilityRole="button"
            accessibilityLabel={connectLabel}
            style={({ pressed }) => [styles.connectBtn, pressed && styles.pressed, busy && styles.disabled]}
          >
            {busy ? (
              <ActivityIndicator size="small" color={colors.accent} />
            ) : (
              <Text style={styles.connectText}>{connectLabel}</Text>
            )}
          </Pressable>
        ) : null}
      </View>
      {children}
      {showHealth && healthLabel ? (
        <View style={styles.health}>
          <View style={styles.healthDot} />
          <Text style={styles.healthText}>{healthLabel}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: spacing.lg,
    gap: spacing.md,
    shadowColor: '#10221A',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.07,
    shadowRadius: 10,
    elevation: 3,
  },
  head: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  headTop: { alignItems: 'flex-start' },
  headCenter: { alignItems: 'center' },
  meta: { flex: 1, gap: 3, minWidth: 0 },
  title: {
    color: colors.text,
    fontFamily: fonts.bodyMedium,
    fontSize: 17,
    fontWeight: '700',
  },
  subtitle: {
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 13,
  },
  pill: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 3,
    marginTop: 4,
  },
  pillOn: { backgroundColor: colors.accentSoft },
  pillOff: { backgroundColor: '#EEF1F1' },
  pillText: { fontFamily: fonts.bodyMedium, fontSize: 12 },
  pillTextOn: { color: colors.accent },
  pillTextOff: { color: colors.textMuted },
  menuBtn: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: -4,
    marginRight: -6,
  },
  connectBtn: {
    borderWidth: 1.5,
    borderColor: colors.accent,
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: colors.surface,
    minWidth: 88,
    alignItems: 'center',
  },
  connectText: {
    color: colors.accent,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '600',
  },
  health: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 2 },
  healthDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.accent,
  },
  healthText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 },
  pressed: { opacity: 0.6 },
  disabled: { opacity: 0.5 },
});
