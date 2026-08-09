import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { colors, fonts, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';

const UsageSchema = z.object({ success: z.literal(true) }).passthrough();

type Props = { onBack: () => void };

export function UsageScreen({ onBack }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState('');

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const data = await apiFetch('/api/mobile/usage', { schema: UsageSchema });
        setPayload(JSON.stringify(data, null, 2));
        setError(null);
      } catch {
        setError('Could not load usage.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <ScreenChrome title="Usage & Credits" subtitle="Included period balance" onBack={onBack}>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView>
        {payload ? (
          <Text style={styles.mono}>{payload}</Text>
        ) : !loading ? (
          <EmptyState title="No usage data" />
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  mono: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
