import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { PLAN_ORDER, type PlanId } from './planCatalog';
import { PLAN_NAME_KEY } from './planEntitlements';

type Props = {
  selected: PlanId;
  currentPlan: PlanId | null;
  tr: (key: StringKey) => string;
  onSelect: (id: PlanId) => void;
};

export function PlanChipRow({ selected, currentPlan, tr, onSelect }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
      >
        {PLAN_ORDER.map((id) => {
          const active = id === selected;
          const isCurrent = id === currentPlan;
          return (
            <Pressable
              key={id}
              onPress={() => onSelect(id)}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              accessibilityLabel={
                isCurrent ? `${tr(PLAN_NAME_KEY[id])} ${tr('subYourPlan')}` : tr(PLAN_NAME_KEY[id])
              }
              style={[
                styles.chip,
                {
                  backgroundColor: active ? colors.accent : colors.surface,
                  borderColor: active ? colors.accent : isCurrent ? colors.accent : colors.border,
                },
              ]}
            >
              <Text
                style={[
                  styles.label,
                  { color: active ? colors.onAccent : isCurrent ? colors.accent : colors.text },
                ]}
              >
                {tr(PLAN_NAME_KEY[id])}
              </Text>
              {isCurrent ? (
                <Text
                  style={[
                    styles.caption,
                    { color: active ? colors.onAccent : colors.accent },
                  ]}
                >
                  {tr('subYourPlan')}
                </Text>
              ) : null}
            </Pressable>
          );
        })}
      </ScrollView>
      <Text style={[styles.hint, { color: colors.textMuted }]}>{tr('subTapToCompare')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8 },
  row: { gap: 8, paddingRight: 8 },
  chip: {
    borderWidth: 1.5,
    borderRadius: radii.pill,
    paddingHorizontal: 16,
    paddingVertical: 8,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: { fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '600' },
  caption: { fontFamily: fonts.body, fontSize: 10, marginTop: 1 },
  hint: { fontFamily: fonts.body, fontSize: 13 },
});
