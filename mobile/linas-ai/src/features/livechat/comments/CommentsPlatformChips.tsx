import { Pressable, StyleSheet, View } from 'react-native';

import { AppIcon, ion } from '../../../components/AppIcon';
import { radii, useTheme } from '../../../theme';
import type { CommentPlatform } from './commentsInboxTypes';

export const COMMENT_CHANNEL_CHIPS: {
  id: CommentPlatform;
  icon: ReturnType<typeof ion>;
  color: string;
  bg: string;
}[] = [
  { id: 'instagram', icon: ion('logo-instagram'), color: '#E1306C', bg: '#FCE7F3' },
  { id: 'facebook', icon: ion('logo-facebook'), color: '#1877F2', bg: '#E8F1FF' },
  { id: 'tiktok', icon: ion('logo-tiktok'), color: '#111111', bg: '#F3F4F6' },
];

const CHIPS = COMMENT_CHANNEL_CHIPS;

export function CommentChannelIcon({ platform, size = 16 }: { platform: string; size?: number }) {
  const chip = CHIPS.find((row) => row.id === platform) || CHIPS[0];
  return <AppIcon icon={chip.icon} size={size} color={chip.color} />;
}

type Props = {
  selected: CommentPlatform;
  onSelect: (id: CommentPlatform) => void;
  allowed?: string[] | null;
};

export function allowedCommentPlatforms(allowed?: string[] | null): CommentPlatform[] {
  const ids = CHIPS.map((chip) => chip.id);
  if (!allowed) return ids;
  return ids.filter((id) => allowed.includes(id));
}

export function CommentsPlatformChips({ selected, onSelect, allowed }: Props) {
  const { colors } = useTheme();
  const chips = CHIPS.filter((chip) => !allowed || allowed.includes(chip.id));
  if (chips.length === 0) return null;
  return (
    <View style={styles.row} accessibilityRole="tablist">
      {chips.map((chip) => {
        const on = selected === chip.id;
        return (
          <Pressable
            key={chip.id}
            onPress={() => onSelect(chip.id)}
            style={[
              styles.chip,
              {
                backgroundColor: on ? chip.bg : colors.surface,
                borderColor: on ? chip.color : colors.border,
              },
            ]}
            accessibilityRole="tab"
            accessibilityLabel={chip.id}
            accessibilityState={{ selected: on }}
          >
            <AppIcon icon={chip.icon} size={22} color={chip.color} />
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  chip: {
    width: 44,
    height: 44,
    borderRadius: radii.pill,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
