import { useEffect, useState } from 'react';
import {
  Keyboard,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
} from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';

export type PlusAction = 'attach_image' | 'attach_document';

export type PlusAnchor = { x: number; y: number; width: number; height: number };

type Props = {
  open: boolean;
  onClose: () => void;
  onAction: (action: PlusAction) => void;
  anchor?: PlusAnchor | null;
};

const MENU_W = 220;
const COMPOSER_GAP = 72;
const PICKER_DELAY_MS = Platform.OS === 'ios' ? 400 : 80;

/** White rounded Photos/Files popover above the composer +, left-aligned. */
export function ComposerPlusMenu({ open, onClose, onAction, anchor }: Props) {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const [kb, setKb] = useState(0);

  useEffect(() => {
    const showEvt = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvt = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const show = Keyboard.addListener(showEvt, (e) => setKb(e.endCoordinates.height));
    const hide = Keyboard.addListener(hideEvt, () => setKb(0));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);

  const rows: { id: PlusAction; title: string; icon: 'image' | 'paperclip' }[] = [
    { id: 'attach_image', title: tr('photos'), icon: 'image' },
    { id: 'attach_document', title: tr('files'), icon: 'paperclip' },
  ];

  function choose(action: PlusAction) {
    onClose();
    setTimeout(() => onAction(action), PICKER_DELAY_MS);
  }

  return (
    <Modal
      visible={open}
      transparent
      animationType="fade"
      onRequestClose={onClose}
      statusBarTranslucent
      presentationStyle="overFullScreen"
    >
      <Pressable style={styles.scrim} onPress={onClose}>
        <Pressable
          style={[
            styles.menu,
            {
              backgroundColor: colors.surface,
              shadowColor: colors.text,
              left: anchor ? Math.max(spacing.md, anchor.x) : spacing.md,
              bottom: anchor ? undefined : kb + COMPOSER_GAP,
              top: anchor ? Math.max(spacing.sm, anchor.y - 120) : undefined,
            },
          ]}
          onPress={(e) => e.stopPropagation()}
        >
          {rows.map((row) => (
            <Pressable
              key={row.id}
              style={styles.row}
              onPress={() => choose(row.id)}
              accessibilityRole="button"
              accessibilityLabel={row.title}
            >
              <AppIcon icon={feather(row.icon)} size={20} color={colors.textMuted} />
              <Text style={[styles.label, { color: colors.text }]}>{row.title}</Text>
            </Pressable>
          ))}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: 'transparent',
  },
  menu: {
    position: 'absolute',
    width: MENU_W,
    borderRadius: radii.lg,
    paddingVertical: 6,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.14,
    shadowRadius: 14,
    elevation: 10,
    direction: 'ltr',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: 12,
    gap: spacing.md,
  },
  label: {
    fontFamily: fonts.body,
    fontSize: 16,
  },
});
