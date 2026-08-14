import { Text, TextInput, View, type StyleProp, type ViewStyle } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { aiLimitsStyles } from './aiLimitsStyles';

type Props = {
  value: string;
  onChange: (value: string) => void;
  suffix?: string;
  style?: StyleProp<ViewStyle>;
};

export function AiLimitsPencilField({ value, onChange, suffix, style }: Props) {
  return (
    <View style={[aiLimitsStyles.field, style]}>
      <TextInput
        value={value}
        onChangeText={onChange}
        keyboardType="number-pad"
        style={aiLimitsStyles.input}
      />
      {suffix ? <Text style={aiLimitsStyles.suffix}>{suffix}</Text> : null}
      <AppIcon icon={feather('edit-2')} size={16} color="#8A9A98" />
    </View>
  );
}
