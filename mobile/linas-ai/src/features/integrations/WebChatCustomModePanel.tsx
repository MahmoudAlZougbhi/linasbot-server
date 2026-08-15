import * as Clipboard from 'expo-clipboard';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import type { WebChatSettings } from './webChatApi';

type Props = {
  settings: WebChatSettings;
  busy?: boolean;
  onRotateKey: () => void;
  onTestConnection: () => void;
  onNotice: (message: string) => void;
};

export function WebChatCustomModePanel({
  settings,
  busy,
  onRotateKey,
  onTestConnection,
  onNotice,
}: Props) {
  const { tr } = useI18n();

  async function copyId() {
    await Clipboard.setStringAsync(settings.integration_public_id);
    onNotice(tr('webChatIdCopied'));
  }

  async function openDocs() {
    const url = settings.sdk_docs_url || `${settings.widget_script_url.replace('/web-chat/widget.js', '')}/web-chat/sdk-docs`;
    await Clipboard.setStringAsync(url);
    onNotice(tr('webChatDocsCopied'));
    void Linking.openURL(url);
  }

  return (
    <View style={styles.wrap}>
      <Text style={styles.section}>{tr('webChatDeveloperTitle')}</Text>
      <Text style={styles.label}>{tr('webChatAllowedDomain')}</Text>
      <Text style={styles.value}>{settings.site_url || '—'}</Text>

      <Text style={styles.label}>{tr('webChatPublicId')}</Text>
      <Text selectable style={styles.code}>
        {settings.integration_public_id}
      </Text>
      <Pressable disabled={busy} onPress={() => void copyId()} style={styles.linkBtn}>
        <Text style={styles.linkText}>{tr('webChatCopyId')}</Text>
      </Pressable>

      <Pressable disabled={busy} onPress={onTestConnection} style={styles.btn}>
        <Text style={styles.btnText}>{tr('webChatTestConnection')}</Text>
      </Pressable>

      <Pressable disabled={busy} onPress={() => void openDocs()} style={styles.linkBtn}>
        <Text style={styles.linkText}>{tr('webChatSetupDocs')}</Text>
      </Pressable>

      <Pressable disabled={busy} onPress={onRotateKey} style={styles.linkBtn}>
        <Text style={[styles.linkText, styles.destructive]}>{tr('webChatRotateKeyMenu')}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  section: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.text },
  label: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted },
  value: { fontFamily: fonts.body, fontSize: 14, color: colors.text },
  code: {
    fontFamily: fonts.body,
    fontSize: 12,
    color: colors.textMuted,
    backgroundColor: colors.input,
    padding: spacing.sm,
    borderRadius: radii.sm,
  },
  btn: {
    alignSelf: 'flex-start',
    backgroundColor: colors.accent,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
  },
  btnText: { fontFamily: fonts.bodyMedium, color: '#fff', fontSize: 14 },
  linkBtn: { paddingVertical: 4 },
  linkText: { fontFamily: fonts.bodyMedium, color: colors.accent, fontSize: 14 },
  destructive: { color: colors.warning },
});
