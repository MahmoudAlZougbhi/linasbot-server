import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../theme';
import type { OwnerChatMode } from './ownerChatMode';

type Props = {
  mode: OwnerChatMode;
  onChange: (mode: OwnerChatMode) => void;
};

/** Segmented Chat | Work control on a new thread. Work = high, Chat = low. */
export function ChatModeToggle({ mode, onChange }: Props) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.wrap,
        {
          backgroundColor: colors.bgElevated,
          borderColor: colors.borderSoft,
          shadowColor: colors.text,
        },
      ]}
      accessibilityRole="tablist"
    >
      {(['chat', 'work'] as const).map((id) => {
        const selected = mode === id;
        return (
          <Pressable
            key={id}
            onPress={() => onChange(id)}
            style={[
              styles.seg,
              selected && { backgroundColor: colors.surfaceAlt },
            ]}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={id === 'chat' ? 'Chat mode' : 'Work mode'}
          >
            <Text
              style={[
                styles.label,
                { color: colors.text, fontFamily: selected ? fonts.bodyMedium : fonts.body },
              ]}
            >
              {id === 'chat' ? 'Chat' : 'Work'}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignSelf: 'center',
    flexDirection: 'row',
    borderRadius: radii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    padding: 3,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 1,
  },
  seg: {
    minWidth: 72,
    paddingHorizontal: 18,
    paddingVertical: 8,
    borderRadius: radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    fontSize: 14,
  },
});
