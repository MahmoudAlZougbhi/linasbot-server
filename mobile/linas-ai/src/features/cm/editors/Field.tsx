import { Text, View } from 'react-native';

import { TextField } from '../../../components/TextField';
import { AI_SETUP_INK } from '../aiSetupDesign';
import { ClampedLongField } from '../ClampedLongField';
import { cmFormStyles } from '../cmFormStyles';

type Props = {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
  placeholder?: string;
  hint?: string;
};

export function Field({ label, value, onChange, multiline, placeholder, hint }: Props) {
  if (multiline) {
    return (
      <ClampedLongField
        label={label}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        hint={hint}
        labelStyle={cmFormStyles.label}
        hintStyle={cmFormStyles.hint}
      />
    );
  }
  return (
    <View>
      {label ? <Text style={cmFormStyles.label}>{label}</Text> : null}
      <TextField
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        style={{ color: AI_SETUP_INK }}
      />
      {hint ? <Text style={cmFormStyles.hint}>{hint}</Text> : null}
    </View>
  );
}
