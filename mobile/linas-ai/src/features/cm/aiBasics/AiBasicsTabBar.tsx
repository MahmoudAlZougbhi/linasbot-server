import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts } from '../../../theme';
import { AB_BORDER, AB_FOREST, AB_RADIUS_SM, AB_TEXT } from './aiBasicsChrome';

export type AiBasicsTab = 'identity' | 'style' | 'greetings';

type Props = {
  tab: AiBasicsTab;
  labels: { identity: string; style: string; greetings: string };
  onChange: (tab: AiBasicsTab) => void;
};

const ORDER: AiBasicsTab[] = ['identity', 'style', 'greetings'];

export function AiBasicsTabBar({ tab, labels, onChange }: Props) {
  return (
    <View style={styles.row} accessibilityRole="tablist">
      {ORDER.map((id) => {
        const on = tab === id;
        return (
          <Pressable
            key={id}
            onPress={() => onChange(id)}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            style={[styles.chip, on && styles.chipOn]}
          >
            <Text style={[styles.text, on && styles.textOn]} numberOfLines={1}>
              {labels[id]}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 16,
  },
  chip: {
    flex: 1,
    minHeight: 40,
    borderRadius: AB_RADIUS_SM,
    borderWidth: 1,
    borderColor: AB_BORDER,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  chipOn: { backgroundColor: AB_FOREST, borderColor: AB_FOREST },
  text: { color: AB_TEXT, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  textOn: { color: '#FFFFFF' },
});
