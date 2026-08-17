/** Authenticated product media thumbnail (bearer → data URI). */

import { useEffect, useState, type ReactNode } from 'react';
import { ActivityIndicator, Image, StyleSheet, View, type ImageStyle, type StyleProp } from 'react-native';

import { API_BASE } from '../../api/client';
import { tokenStore } from '../../auth/tokenStore';
import { PR_TEAL, PR_TEAL_SOFT } from './productChrome';

type Props = {
  mediaId?: string | null;
  style?: StyleProp<ImageStyle>;
  placeholderIcon?: ReactNode;
};

export function productMediaUrl(mediaId: string): string {
  return `${API_BASE}/api/mobile/products/media/${encodeURIComponent(mediaId)}`;
}

export function ProductAuthImage({ mediaId, style, placeholderIcon }: Props) {
  const [uri, setUri] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!mediaId) {
      setUri(null);
      setFailed(false);
      return;
    }
    let cancelled = false;
    setUri(null);
    setFailed(false);
    void (async () => {
      try {
        const access = await tokenStore.getAccessToken();
        const res = await fetch(productMediaUrl(mediaId), {
          headers: access ? { Authorization: `Bearer ${access}` } : {},
        });
        if (!res.ok) throw new Error('media');
        const buf = await res.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        const b64 = globalThis.btoa(binary);
        const ct = res.headers.get('content-type') || 'image/jpeg';
        if (!cancelled) setUri(`data:${ct};base64,${b64}`);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mediaId]);

  if (!mediaId || failed) {
    return <View style={[styles.ph, style as object]}>{placeholderIcon}</View>;
  }
  if (!uri) {
    return (
      <View style={[styles.ph, style as object]}>
        <ActivityIndicator color={PR_TEAL} />
      </View>
    );
  }
  return <Image source={{ uri }} style={style} resizeMode="cover" />;
}

const styles = StyleSheet.create({
  ph: {
    backgroundColor: PR_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
});
