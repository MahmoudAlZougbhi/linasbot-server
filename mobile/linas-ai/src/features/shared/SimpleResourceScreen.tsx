import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text } from 'react-native';
import { z } from 'zod';

import { apiFetch } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { colors, fonts, spacing } from '../../theme';
import { ScreenChrome } from './ScreenChrome';

type Props = {
  title: string;
  path: string;
  onBack: () => void;
};

const LooseSchema = z.object({ success: z.boolean() }).passthrough();

export function SimpleResourceScreen({ title, path, onBack }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState('');

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch(path, { schema: LooseSchema });
        if (!cancelled) {
          setPayload(JSON.stringify(data, null, 2));
        }
      } catch {
        if (!cancelled) {
          setError('Failed to load. Go back and open again to retry.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [path]);

  return (
    <ScreenChrome title={title} onBack={onBack}>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <ScrollView>
        {payload ? (
          <Text style={styles.mono}>{payload}</Text>
        ) : !loading && !error ? (
          <EmptyState title="No data" />
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  mono: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
