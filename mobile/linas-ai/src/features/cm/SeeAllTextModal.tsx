import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather } from '../../components/AppIcon';
import { AppModal } from '../../components/AppModal';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts } from '../../theme';
import { AI_SETUP_TEAL } from './aiSetupDesign';

const TEAL_DARK = '#0F4C4A';

type Props = {
  visible: boolean;
  title: string;
  text: string;
  onClose: () => void;
};

/** Full-screen Note/Description reader — Copy + X, then back to the same editor. */
export function SeeAllTextModal({ visible, title, text, onClose }: Props) {
  const insets = useSafeAreaInsets();
  const { tr } = useI18n();
  const [copied, setCopied] = useState(false);

  async function copyAll() {
    await Clipboard.setStringAsync(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  return (
    <AppModal visible={visible} animationType="fade" onRequestClose={onClose}>
      <View style={[styles.root, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 12 }]}>
        <View style={styles.bar}>
          <Pressable
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel={tr('back')}
            style={styles.iconBtn}
          >
            <AppIcon icon={feather('x')} size={22} color={TEAL_DARK} />
          </Pressable>
          <Text style={styles.title} numberOfLines={1}>
            {title}
          </Text>
          <Pressable
            onPress={() => void copyAll()}
            accessibilityRole="button"
            accessibilityLabel={tr('aiSetupCopy')}
            style={styles.copyBtn}
          >
            <Text style={styles.copyText}>{copied ? tr('aiSetupCopied') : tr('aiSetupCopy')}</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator>
          <Text style={styles.text}>{text}</Text>
        </ScrollView>
      </View>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 12,
    paddingBottom: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#D7E4E2',
  },
  iconBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  title: {
    flex: 1,
    color: TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 17,
    fontWeight: '700',
  },
  copyBtn: {
    borderWidth: 1.5,
    borderColor: AI_SETUP_TEAL,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  copyText: { color: AI_SETUP_TEAL, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
  body: { paddingHorizontal: 20, paddingVertical: 16, paddingBottom: 48 },
  text: {
    color: TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: 24,
  },
});
