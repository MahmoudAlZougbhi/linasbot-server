import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { APP_VERSION_LABEL, LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { NewChatIcon } from '../chat/ChatHeaderIcons';
import { DRAWER_TOOL_ICONS } from './moduleIcons';

type Props = {
  isAuthenticated: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onOpenSettings: () => void;
  onLogin?: () => void;
  onRegister?: () => void;
};

export function DrawerFooter(props: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View style={styles.wrap}>
      {!props.isAuthenticated ? (
        <View style={styles.authBlock}>
          <Pressable
            onPress={() => {
              props.onClose();
              props.onLogin?.();
            }}
            style={styles.authRow}
            accessibilityRole="button"
            accessibilityLabel={tr('login')}
          >
            <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>{tr('login')}</Text>
          </Pressable>
          <Pressable
            onPress={() => {
              props.onClose();
              props.onRegister?.();
            }}
            style={styles.authRow}
            accessibilityRole="button"
            accessibilityLabel={tr('createAccount')}
          >
            <Text style={{ color: colors.text }}>{tr('createAccount')}</Text>
          </Pressable>
          <View style={styles.legalRow}>
            <Pressable
              onPress={() => void Linking.openURL(LEGAL_URLS.privacy)}
              accessibilityRole="link"
              accessibilityLabel={tr('privacy')}
            >
              <Text style={{ color: colors.accent, fontSize: 11 }}>{tr('privacy')}</Text>
            </Pressable>
            <Text style={{ color: colors.textDim, fontSize: 11 }}> · </Text>
            <Pressable
              onPress={() => void Linking.openURL(LEGAL_URLS.terms)}
              accessibilityRole="link"
              accessibilityLabel={tr('terms')}
            >
              <Text style={{ color: colors.accent, fontSize: 11 }}>{tr('terms')}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      <View style={styles.actionRow}>
        <Pressable
          style={[styles.newChatBtn, { backgroundColor: colors.accentDeep }]}
          onPress={() => {
            props.onNewChat();
            props.onClose();
          }}
          accessibilityRole="button"
          accessibilityLabel={tr('newChat')}
        >
          <NewChatIcon color={colors.onAccent} size={16} />
          <Text style={[styles.newChatText, { color: colors.onAccent }]}>{tr('newChat')}</Text>
        </Pressable>
        <Pressable
          style={[styles.settingsBtn, { backgroundColor: colors.surface, borderColor: colors.borderSoft }]}
          onPress={() => {
            props.onClose();
            props.onOpenSettings();
          }}
          accessibilityRole="button"
          accessibilityLabel={tr('settings')}
        >
          <AppIcon icon={DRAWER_TOOL_ICONS.settings} size={20} color={colors.accentDeep} />
        </Pressable>
      </View>

      <Text
        style={[styles.version, { color: colors.textDim }]}
        numberOfLines={1}
        accessibilityRole="text"
        accessibilityLabel={APP_VERSION_LABEL}
      >
        {APP_VERSION_LABEL}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingTop: spacing.sm, gap: spacing.sm },
  authBlock: { gap: 2, marginBottom: spacing.xs },
  authRow: { minHeight: 36, justifyContent: 'center' },
  legalRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  newChatBtn: {
    flex: 1,
    minHeight: 40,
    borderRadius: radii.pill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
  },
  newChatText: {
    fontFamily: fonts.display,
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: -0.15,
  },
  settingsBtn: {
    width: 42,
    height: 42,
    borderRadius: 21,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 3,
    elevation: 2,
  },
  version: {
    fontFamily: fonts.body,
    fontSize: 11,
    textAlign: 'center',
    marginTop: 2,
  },
});

/** @deprecated Use DrawerFooter */
export function NavDrawerFooter(
  props: Omit<Props, 'onOpenSettings'> & { workspaceLabel?: string | null },
) {
  return (
    <DrawerFooter
      isAuthenticated={props.isAuthenticated}
      onClose={props.onClose}
      onNewChat={props.onNewChat}
      onOpenSettings={() => {}}
      onLogin={props.onLogin}
      onRegister={props.onRegister}
    />
  );
}
