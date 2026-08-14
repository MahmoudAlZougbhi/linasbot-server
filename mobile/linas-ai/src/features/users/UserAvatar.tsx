import { StyleSheet, Text, View } from 'react-native';

import { colors, fonts } from '../../theme';
import { userInitials } from './usersAccess';

type Props = {
  name: string;
  email: string;
  size?: number;
};

export function UserAvatar({ name, email, size = 44 }: Props) {
  const initials = userInitials(name, email);
  return (
    <View
      style={[
        styles.wrap,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
        },
      ]}
    >
      <Text style={[styles.letters, { fontSize: size < 40 ? 13 : 15 }]}>{initials}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.accentSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  letters: {
    color: colors.accentDeep,
    fontFamily: fonts.bodyMedium,
    fontWeight: '700',
  },
});
