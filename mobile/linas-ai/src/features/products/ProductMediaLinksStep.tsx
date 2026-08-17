import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useState } from 'react';

import { AppIcon, feather } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { ProductChannelLinksCard } from './ProductChannelLinksCard';
import {
  PR_BORDER,
  PR_INK,
  PR_MUTED,
  PR_RADIUS,
  PR_RADIUS_SM,
  PR_SLOT_H,
  PR_TEAL,
  PR_TEAL_SOFT,
} from './productChrome';
import type { AssetRef, ChannelLink, ChannelPlatform, ShareableLink } from './productModel';
import { MAX_PRODUCT_IMAGES } from './productsApi';

type ImageRow = { media_id: string; sort_order: number; previewUri?: string };

type Props = {
  images: ImageRow[];
  video: AssetRef | null;
  file: AssetRef | null;
  shareable: ShareableLink[];
  channel: ChannelLink[];
  uploading: boolean;
  saving: boolean;
  onAddImage: () => void;
  onRemoveImage: (mediaId: string) => void;
  onAddVideo: () => void;
  onClearVideo: () => void;
  onAddFile: () => void;
  onClearFile: () => void;
  onAddShareable: (url: string) => void;
  onRemoveShareable: (index: number) => void;
  onAddChannel: (platform: ChannelPlatform, url: string) => void;
  onRemoveChannel: (index: number) => void;
  onSave: () => void;
  tr: (key: StringKey) => string;
};

export function ProductMediaLinksStep({
  images,
  video,
  file,
  shareable,
  channel,
  uploading,
  saving,
  onAddImage,
  onRemoveImage,
  onAddVideo,
  onClearVideo,
  onAddFile,
  onClearFile,
  onAddShareable,
  onRemoveShareable,
  onAddChannel,
  onRemoveChannel,
  onSave,
  tr,
}: Props) {
  const [shareUrl, setShareUrl] = useState('');
  const slots = Math.max(MAX_PRODUCT_IMAGES - 1, images.length + (images.length < MAX_PRODUCT_IMAGES ? 1 : 0));
  const slotCount = Math.min(MAX_PRODUCT_IMAGES, Math.max(4, slots));

  return (
    <View style={styles.wrap}>
      <View style={styles.card}>
        <Text style={styles.h}>{tr('productsMediaSection')}</Text>
        <Text style={styles.sub}>{tr('productsMediaHint')}</Text>
        <View style={styles.slots}>
          {Array.from({ length: slotCount }).map((_, index) => {
            const img = images[index];
            if (img) {
              return (
                <Pressable
                  key={img.media_id}
                  onLongPress={() => onRemoveImage(img.media_id)}
                  style={styles.slotFilled}
                >
                  {img.previewUri ? (
                    <Image source={{ uri: img.previewUri }} style={styles.slotImg} />
                  ) : (
                    <View style={[styles.slotImg, styles.slotPh]}>
                      <AppIcon icon={feather('image')} size={18} color={PR_TEAL} />
                    </View>
                  )}
                </Pressable>
              );
            }
            const isAdd = index === images.length && images.length < MAX_PRODUCT_IMAGES;
            return (
              <Pressable
                key={`empty-${index}`}
                onPress={isAdd ? onAddImage : undefined}
                disabled={!isAdd || uploading}
                style={[styles.slotEmpty, isAdd && styles.slotAdd]}
              >
                {isAdd ? (
                  uploading ? (
                    <ActivityIndicator color={PR_TEAL} />
                  ) : (
                    <>
                      <AppIcon icon={feather('image')} size={18} color={PR_TEAL} />
                      <Text style={styles.slotAddText}>{tr('productsAddImageShort')}</Text>
                    </>
                  )
                ) : null}
              </Pressable>
            );
          })}
        </View>
        <View style={styles.mediaRow}>
          <Pressable
            onPress={onAddVideo}
            disabled={uploading || Boolean(video)}
            style={({ pressed }) => [styles.mediaBtn, pressed && styles.pressed]}
          >
            <AppIcon icon={feather('play-circle')} size={18} color={PR_TEAL} />
            <Text style={styles.mediaBtnText}>
              {video ? tr('productsVideoAdded') : tr('productsAddVideo')}
            </Text>
          </Pressable>
          <Pressable
            onPress={onAddFile}
            disabled={uploading || Boolean(file)}
            style={({ pressed }) => [styles.mediaBtn, pressed && styles.pressed]}
          >
            <AppIcon icon={feather('file')} size={18} color={PR_TEAL} />
            <Text style={styles.mediaBtnText}>
              {file ? tr('productsFileAdded') : tr('productsAddFile')}
            </Text>
          </Pressable>
        </View>
        {video ? (
          <Pressable onPress={onClearVideo}>
            <Text style={styles.clear}>{tr('productsRemoveVideo')}</Text>
          </Pressable>
        ) : null}
        {file ? (
          <Pressable onPress={onClearFile}>
            <Text style={styles.clear}>{tr('productsRemoveFile')}</Text>
          </Pressable>
        ) : null}
      </View>

      <View style={styles.card}>
        <Text style={styles.h}>{tr('productsShareLinksSection')}</Text>
        <Text style={styles.sub}>{tr('productsShareLinksHint')}</Text>
        {shareable.map((row, index) => (
          <View key={`share-${index}`} style={styles.linkRow}>
            <Text style={styles.linkUrl} numberOfLines={1}>
              {row.url}
            </Text>
            <Pressable onPress={() => onRemoveShareable(index)}>
              <AppIcon icon={feather('x')} size={16} color={PR_MUTED} />
            </Pressable>
          </View>
        ))}
        <TextInput
          value={shareUrl}
          onChangeText={setShareUrl}
          placeholder={tr('productsShareLinkPlaceholder')}
          placeholderTextColor={PR_MUTED}
          autoCapitalize="none"
          autoCorrect={false}
          style={styles.input}
        />
        <Pressable
          onPress={() => {
            if (!shareUrl.trim()) return;
            onAddShareable(shareUrl.trim());
            setShareUrl('');
          }}
          style={({ pressed }) => [styles.outlineBtn, pressed && styles.pressed]}
        >
          <Text style={styles.outlineBtnText}>{tr('productsAddShareLink')}</Text>
        </Pressable>
      </View>

      <ProductChannelLinksCard
        channel={channel}
        onAddChannel={onAddChannel}
        onRemoveChannel={onRemoveChannel}
        tr={tr}
      />

      <Pressable
        onPress={onSave}
        disabled={saving || uploading}
        accessibilityRole="button"
        style={({ pressed }) => [styles.saveBtn, (pressed || saving) && styles.pressed]}
      >
        {saving ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text style={styles.saveText}>{tr('productsSave')}</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 14, paddingBottom: 28 },
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
  slots: { flexDirection: 'row', gap: 8 },
  slotEmpty: {
    flex: 1,
    height: PR_SLOT_H,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PR_BORDER,
    backgroundColor: '#FFFFFF',
  },
  slotAdd: {
    borderStyle: 'dashed',
    borderColor: PR_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    backgroundColor: PR_TEAL_SOFT,
  },
  slotAddText: { color: PR_TEAL, fontFamily: fonts.bodyMedium, fontSize: 11, fontWeight: '700' },
  slotFilled: { flex: 1, height: PR_SLOT_H, borderRadius: 12, overflow: 'hidden' },
  slotImg: { width: '100%', height: '100%' },
  slotPh: { backgroundColor: PR_TEAL_SOFT, alignItems: 'center', justifyContent: 'center' },
  mediaRow: { flexDirection: 'row', gap: 8 },
  mediaBtn: {
    flex: 1,
    minHeight: 44,
    borderRadius: PR_RADIUS_SM,
    borderWidth: 1,
    borderColor: PR_BORDER,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: '#FFFFFF',
  },
  mediaBtnText: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  clear: { color: PR_TEAL, fontFamily: fonts.bodyMedium, fontSize: 13 },
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
  outlineBtn: {
    borderWidth: 1,
    borderColor: PR_BORDER,
    borderRadius: PR_RADIUS_SM,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  outlineBtnText: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '600' },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: PR_BORDER,
  },
  linkUrl: { flex: 1, color: PR_INK, fontFamily: fonts.body, fontSize: 13 },
  saveBtn: {
    backgroundColor: PR_TEAL,
    borderRadius: 999,
    minHeight: 50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  pressed: { opacity: 0.75 },
});
