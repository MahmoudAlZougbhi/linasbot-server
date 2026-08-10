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
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch(path, { schema: LooseSchema });
        if (!cancelled) {
          setLoaded(true);
          setPayload(__DEV__ ? JSON.stringify(data, null, 2) : '');
        }
      } catch {
        if (!cancelled) {
          setLoaded(false);
          setError('Something went wrong. Please go back and try again.');
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
        {__DEV__ && payload ? (
          <Text style={styles.mono}>{payload}</Text>
        ) : !loading && !error && loaded ? (
          <EmptyState title="Ready" body="This section loaded successfully." />
        ) : !loading && !error ? (
          <EmptyState title="Nothing to show" body="Please try again later." />
        ) : null}
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  mono: { color: colors.textMuted, fontFamily: 'Courier', fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, marginBottom: spacing.md, fontFamily: fonts.body },
});
