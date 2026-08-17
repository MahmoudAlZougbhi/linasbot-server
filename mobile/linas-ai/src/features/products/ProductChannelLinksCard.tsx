/** Channel video links block for Products media step. */

import { Modal, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useState } from 'react';

import { AppIcon, feather } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { PR_BORDER, PR_INK, PR_MUTED, PR_RADIUS, PR_RADIUS_SM, PR_TEAL, PR_TEAL_SOFT } from './productChrome';
import {
  CHANNEL_PLATFORMS,
  platformLabel,
  type ChannelLink,
  type ChannelPlatform,
} from './productModel';

type Props = {
  channel: ChannelLink[];
  onAddChannel: (platform: ChannelPlatform, url: string) => void;
  onRemoveChannel: (index: number) => void;
  tr: (key: StringKey) => string;
};

export function ProductChannelLinksCard({ channel, onAddChannel, onRemoveChannel, tr }: Props) {
  const [channelUrl, setChannelUrl] = useState('');
  const [platform, setPlatform] = useState<ChannelPlatform>('instagram');
  const [platformOpen, setPlatformOpen] = useState(false);

  return (
    <View style={styles.card}>
      <Text style={styles.h}>{tr('productsChannelSection')}</Text>
      <Text style={styles.sub}>{tr('productsChannelHint')}</Text>
      <View style={styles.infoBanner}>
        <Text style={styles.infoText}>{tr('productsChannelInfo')}</Text>
      </View>
      {channel.map((row, index) => (
        <View key={`ch-${index}`} style={styles.linkRow}>
          <Text style={styles.linkUrl} numberOfLines={1}>
            {platformLabel(row.platform)} · {row.url}
          </Text>
          <Pressable onPress={() => onRemoveChannel(index)}>
            <AppIcon icon={feather('x')} size={16} color={PR_MUTED} />
          </Pressable>
        </View>
      ))}
      <View style={styles.channelRow}>
        <Pressable onPress={() => setPlatformOpen(true)} style={styles.platformBtn} accessibilityRole="button">
          <Text style={styles.platformText}>{platformLabel(platform)}</Text>
          <AppIcon icon={feather('chevron-down')} size={16} color={PR_MUTED} />
        </Pressable>
        <TextInput
          value={channelUrl}
          onChangeText={setChannelUrl}
          placeholder={tr('productsPasteVideoLink')}
          placeholderTextColor={PR_MUTED}
          autoCapitalize="none"
          autoCorrect={false}
          style={[styles.input, styles.channelInput]}
        />
      </View>
      <Pressable
        onPress={() => {
          if (!channelUrl.trim()) return;
          onAddChannel(platform, channelUrl.trim());
          setChannelUrl('');
        }}
        style={({ pressed }) => [styles.outlineBtn, pressed && styles.pressed]}
      >
        <Text style={styles.outlineBtnText}>{tr('productsAddChannelLink')}</Text>
      </Pressable>
      <Text style={styles.platformsLine}>{tr('productsChannelPlatforms')}</Text>

      <Modal visible={platformOpen} transparent animationType="fade" onRequestClose={() => setPlatformOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setPlatformOpen(false)}>
          <View style={styles.modalCard}>
            {CHANNEL_PLATFORMS.map((p) => (
              <Pressable
                key={p}
                onPress={() => {
                  setPlatform(p);
                  setPlatformOpen(false);
                }}
                style={styles.modalRow}
              >
                <Text style={styles.modalRowText}>{platformLabel(p)}</Text>
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: PR_RADIUS,
    borderWidth: 1,
    borderColor: PR_BORDER,
    padding: 14,
    gap: 10,
  },
  h: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  sub: { color: PR_MUTED, fontFamily: fonts.body, fontSize: 13, lineHeight: 18, marginTop: -4 },
  infoBanner: {
    backgroundColor: PR_TEAL_SOFT,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  infoText: { color: PR_TEAL, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: PR_BORDER,
  },
  linkUrl: { flex: 1, color: PR_INK, fontFamily: fonts.body, fontSize: 13 },
  channelRow: { flexDirection: 'row', gap: 8 },
  platformBtn: {
    minWidth: 110,
    borderWidth: 1,
    borderColor: PR_BORDER,
    borderRadius: PR_RADIUS_SM,
    paddingHorizontal: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 4,
    backgroundColor: '#FFFFFF',
  },
  platformText: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  input: {
    borderWidth: 1,
    borderColor: PR_BORDER,
    borderRadius: PR_RADIUS_SM,
    paddingHorizontal: 12,
    paddingVertical: 11,
    color: PR_INK,
    fontFamily: fonts.body,
    fontSize: 14,
    backgroundColor: '#FFFFFF',
  },
  channelInput: { flex: 1, marginBottom: 0 },
  outlineBtn: {
    borderWidth: 1,
    borderColor: PR_BORDER,
    borderRadius: PR_RADIUS_SM,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  outlineBtnText: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '600' },
  platformsLine: { color: PR_MUTED, fontFamily: fonts.body, fontSize: 12, textAlign: 'center' },
  pressed: { opacity: 0.75 },
  modalBg: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.35)',
    justifyContent: 'center',
    padding: 32,
  },
  modalCard: { backgroundColor: '#FFFFFF', borderRadius: 14, overflow: 'hidden' },
  modalRow: {
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: PR_BORDER,
  },
  modalRowText: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 15 },
});
