import { Text, View } from 'react-native';

import { TextField } from '../../../components/TextField';
import { cmFormStyles } from '../cmFormStyles';

type Props = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
  placeholder?: string;
  hint?: string;
};

export function Field({ label, value, onChange, multiline, placeholder, hint }: Props) {
  return (
    <View>
      <Text style={cmFormStyles.label}>{label}</Text>
      <TextField
        value={value}
        onChangeText={onChange}
        multiline={multiline}
        placeholder={placeholder}
      />
      {hint ? <Text style={cmFormStyles.hint}>{hint}</Text> : null}
    </View>
  );
}
