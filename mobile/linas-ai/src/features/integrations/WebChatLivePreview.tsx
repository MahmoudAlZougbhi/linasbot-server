import { StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import type { WebChatAppearance } from './webChatTypes';

type Props = {
  appearance: WebChatAppearance;
};

export function WebChatLivePreview({ appearance }: Props) {
  const { tr } = useI18n();
  const dark = appearance.theme.mode === 'dark';
  const panelBg = dark ? '#0F172A' : '#FFFFFF';
  const surface = dark ? '#1E293B' : '#F8FAFC';
  const accent = appearance.theme.accent_color;

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{tr('webChatPreviewTitle')}</Text>
      <View style={[styles.panel, { backgroundColor: panelBg, borderColor: dark ? '#334155' : '#E2E8F0' }]}>
        <View style={[styles.header, { backgroundColor: accent }]}>
          <Text style={styles.headerTitle}>{appearance.identity.display_name}</Text>
          {appearance.identity.subtitle ? (
            <Text style={styles.headerSub}>{appearance.identity.subtitle}</Text>
          ) : null}
        </View>
        <View style={[styles.body, { backgroundColor: surface }]}>
          <View
            style={[
              styles.bubble,
              styles.visitor,
              {
                backgroundColor: appearance.bubbles.visitor_bg,
              },
            ]}
          >
            <Text style={{ color: appearance.bubbles.visitor_text, fontFamily: fonts.body, fontSize: 13 }}>
              {tr('webChatPreviewVisitor')}
            </Text>
          </View>
          <View
            style={[
              styles.bubble,
              styles.ai,
              {
                backgroundColor: appearance.bubbles.assistant_bg,
                borderColor: dark ? '#334155' : '#E2E8F0',
              },
            ]}
          >
            <Text style={{ color: appearance.bubbles.assistant_text, fontFamily: fonts.body, fontSize: 13 }}>
              {appearance.identity.welcome_message || tr('webChatPreviewAi')}
            </Text>
          </View>
        </View>
        <View style={[styles.launcherRow, appearance.layout.position === 'bottom_left' ? styles.left : styles.right]}>
          <View style={[styles.launcher, { backgroundColor: accent }]}>
            <Text style={styles.launcherText}>
              {appearance.launcher.mode === 'icon_text' ? appearance.launcher.text : '💬'}
            </Text>
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.xs },
  title: { fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.text },
  panel: {
    borderRadius: radii.md,
    borderWidth: 1,
    overflow: 'hidden',
    minHeight: 220,
  },
  header: { padding: spacing.sm },
  headerTitle: { color: '#fff', fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
  headerSub: { color: 'rgba(255,255,255,.9)', fontFamily: fonts.body, fontSize: 11, marginTop: 2 },
  body: { padding: spacing.sm, gap: spacing.xs, minHeight: 120 },
  bubble: { maxWidth: '85%', paddingHorizontal: 10, paddingVertical: 8, borderRadius: 12 },
  visitor: { alignSelf: 'flex-end' },
  ai: { alignSelf: 'flex-start', borderWidth: 1 },
  launcherRow: { padding: spacing.sm },
  left: { alignItems: 'flex-start' },
  right: { alignItems: 'flex-end' },
  launcher: {
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 8,
    minWidth: 44,
    alignItems: 'center',
  },
  launcherText: { color: '#fff', fontFamily: fonts.bodyMedium, fontSize: 13 },
});
