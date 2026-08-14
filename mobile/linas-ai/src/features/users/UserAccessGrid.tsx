import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts } from '../../theme';
import {
  ACCESS_SCREENS,
  accessManageChecked,
  accessViewChecked,
  setAccessColumn,
} from './usersAccess';
import type { PermissionMap } from './usersPermissions';

type Props = {
  permissions: PermissionMap;
  onChange: (next: PermissionMap) => void;
  disabled?: boolean;
};

export function UserAccessGrid({ permissions, onChange, disabled }: Props) {
  const { tr } = useI18n();

  return (
    <View>
      <View style={styles.head}>
        <Text style={styles.section}>{tr('usersAppAccess')}</Text>
        <View style={styles.cols}>
          <Text style={styles.col}>{tr('usersView')}</Text>
          <Text style={styles.col}>{tr('usersManage')}</Text>
        </View>
      </View>
      <Text style={styles.sub}>{tr('usersAppAccessSub')}</Text>
      {ACCESS_SCREENS.map((screen, index) => {
        const viewOn = accessViewChecked(screen, permissions);
        const manageOn = accessManageChecked(screen, permissions);
        return (
          <View key={screen.id} style={[styles.row, index < ACCESS_SCREENS.length - 1 && styles.divider]}>
            <Text style={styles.label}>{tr(screen.labelKey)}</Text>
            <View style={styles.cols}>
              <CheckBox
                checked={viewOn}
                disabled={disabled}
                onToggle={() => onChange(setAccessColumn(permissions, screen, 'view', !viewOn))}
              />
              <CheckBox
                checked={manageOn}
                disabled={disabled}
                onToggle={() => onChange(setAccessColumn(permissions, screen, 'manage', !manageOn))}
              />
            </View>
          </View>
        );
      })}
    </View>
  );
}

function CheckBox({
  checked,
  disabled,
  onToggle,
}: {
  checked: boolean;
  disabled?: boolean;
  onToggle: () => void;
}) {
  return (
    <Pressable
      onPress={onToggle}
      disabled={disabled}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      style={({ pressed }) => [styles.box, checked && styles.boxOn, pressed && styles.pressed]}
    >
      {checked ? <AppIcon icon={feather('check')} size={14} color={colors.onAccent} /> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  section: { fontFamily: fonts.bodyMedium, fontSize: 17, fontWeight: '700', color: colors.text },
  sub: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted, marginTop: 4, marginBottom: 10 },
  cols: { flexDirection: 'row', width: 108, justifyContent: 'space-between', paddingRight: 2 },
  col: {
    width: 44,
    textAlign: 'center',
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    color: colors.textMuted,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 11,
  },
  divider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.borderSoft },
  label: { flex: 1, fontFamily: fonts.body, fontSize: 15, color: colors.text, paddingRight: 8 },
  box: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: '#C5CDCD',
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 11,
  },
  boxOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  pressed: { opacity: 0.7 },
});
