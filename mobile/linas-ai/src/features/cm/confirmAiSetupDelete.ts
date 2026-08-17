import { Alert } from 'react-native';

/** Shared Approve/Delete confirm. Cancel never deletes. */
export function confirmAiSetupDelete(opts: {
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
}): void {
  Alert.alert(opts.title, opts.body, [
    { text: opts.cancelLabel, style: 'cancel' },
    { text: opts.confirmLabel, style: 'destructive', onPress: opts.onConfirm },
  ]);
}
