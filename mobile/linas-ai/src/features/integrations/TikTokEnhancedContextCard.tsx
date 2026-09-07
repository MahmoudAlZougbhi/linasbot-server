import { StyleSheet, Text, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts } from '../../theme';
import type { IntegrationListRow } from './integrationsSchemas';

type Props = {
  row: IntegrationListRow;
  busy: boolean;
  actionsDisabled: boolean;
  tr: (key: StringKey) => string;
  onEnable: () => void;
};

function statusCopy(status: string, tr: (key: StringKey) => string): string {
  if (status === 'waiting_for_permission') return tr('tiktokEnhancedWaiting');
  if (status === 'authorization_required') return tr('tiktokEnhancedAuthRequired');
  if (status === 'identity_authorization_required') return tr('tiktokEnhancedIdentityRequired');
  if (status === 'reauthorization_required') return tr('tiktokEnhancedReauth');
  if (status === 'active') return tr('tiktokEnhancedActive');
  if (status === 'limited') return tr('tiktokEnhancedLimited');
  if (status === 'error') return tr('tiktokEnhancedError');
  return tr('tiktokEnhancedAuthRequired');
}

export function TikTokEnhancedContextCard({ row, busy, actionsDisabled, tr, onEnable }: Props) {
  if (!row.connected) return null;
  const enhanced = row.enhanced_video_context;
  const status = String(enhanced?.status || 'authorization_required');
  const postLevel = row.post_context?.level === 'enhanced' ? tr('tiktokEnhancedLevel') : tr('tiktokEnhancedBasic');
  const showEnable = Boolean(enhanced?.can_authorize) && status !== 'active';
  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{tr('tiktokEnhancedVideoContext')}</Text>
      <Text style={styles.line}>{postLevel}</Text>
      <Text style={styles.line}>{statusCopy(status, tr)}</Text>
      {showEnable ? (
        <PrimaryButton
          label={tr('tiktokEnhancedEnable')}
          onPress={onEnable}
          loading={busy}
          disabled={actionsDisabled}
          variant="ghost"
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 10, gap: 4 },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 14 },
  line: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
});
