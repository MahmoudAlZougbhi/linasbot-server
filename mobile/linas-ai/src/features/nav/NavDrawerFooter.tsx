import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { APP_VERSION_LABEL, LEGAL_URLS } from '../../config';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { NewChatIcon } from '../chat/ChatHeaderIcons';

type Props = {
  isAuthenticated: boolean;
  workspaceLabel?: string | null;
  onClose: () => void;
  onNewChat: () => void;
  onLogin?: () => void;
  onRegister?: () => void;
};

/** Live expo-constants label — shared with Settings via config.ts. */
const VERSION_LABEL = APP_VERSION_LABEL;

/** Tenant/workspace sometimes is just "Linas" — that duplicates VERSION_LABEL without a build. */
function isBareLinasBrand(label: string | null | undefined): boolean {
  return (label || '').trim().toLowerCase() === 'linas';
}

/** Compact dock: optional workspace/auth rows, then version left · New Chat right. */
export function NavDrawerFooter(props: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View style={[styles.bottomDock, { borderTopColor: colors.borderSoft }]}>
      {props.isAuthenticated ? (
        !isBareLinasBrand(props.workspaceLabel) ? (
          <Text style={[styles.workspaceRow, { color: colors.textMuted }]} numberOfLines={1}>
            {props.workspaceLabel || tr('workspace')}
          </Text>
        ) : null
      ) : (
        <>
          <Pressable
            onPress={() => {
              props.onClose();
              props.onLogin?.();
            }}
            style={styles.footerRow}
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
            style={styles.footerRow}
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
        </>
      )}

      <View style={styles.bottomRow}>
        <Text
          style={[styles.version, { color: colors.textDim }]}
          numberOfLines={1}
          accessibilityRole="text"
          accessibilityLabel={VERSION_LABEL}
        >
          {VERSION_LABEL}
        </Text>
        <Pressable
          style={[styles.newChatBtn, { backgroundColor: colors.accent }]}
          onPress={() => {
            props.onNewChat();
            props.onClose();
          }}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel={tr('newChat')}
        >
          <NewChatIcon color={colors.onAccent} size={16} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bottomDock: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: 2,
    gap: 2,
  },
  workspaceRow: {
    marginBottom: 0,
    fontSize: 11,
  },
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    minHeight: 28,
  },
  newChatBtn: {
    width: 28,
    height: 28,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  version: {
    fontFamily: fonts.body,
    fontSize: 11,
    flexShrink: 1,
    textAlign: 'left',
  },
  footerRow: {
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  legalRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
});
