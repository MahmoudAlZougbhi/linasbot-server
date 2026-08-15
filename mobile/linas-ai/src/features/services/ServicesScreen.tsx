import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { deleteService, fetchServices, type Service } from './servicesApi';

type Props = {
  onBack?: () => void;
  onAdd: () => void;
  onEdit: (serviceId: string) => void;
};

export function ServicesScreen({ onBack, onAdd, onEdit }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [services, setServices] = useState<Service[]>([]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchServices();
      setServices(res.services);
      setError(null);
    } catch {
      setError(tr('servicesLoadError'));
    } finally {
      setLoading(false);
    }
  }, [tr]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleDelete = async (serviceId: string) => {
    try {
      await deleteService(serviceId);
      setServices((rows) => rows.filter((row) => row.id !== serviceId));
    } catch {
      setError(tr('servicesDeleteError'));
    }
  };

  return (
    <ScreenChrome title={tr('servicesTitle')} subtitle={tr('servicesSubtitle')} onBack={onBack}>
      {loading ? <ActivityIndicator color={colors.accent} style={styles.loader} /> : null}
      {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
      <PrimaryButton label={tr('servicesAdd')} onPress={onAdd} />
      <FlatList
        data={services}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          !loading ? (
            <Text style={[styles.empty, { color: colors.muted }]}>{tr('servicesEmpty')}</Text>
          ) : null
        }
        renderItem={({ item }) => (
          <View style={[styles.card, { borderColor: colors.border }]}>
            <Pressable onPress={() => onEdit(item.id)} style={styles.cardMain}>
              <Text style={styles.name}>{item.name}</Text>
              {item.price_summary ? (
                <Text style={{ color: colors.muted }}>{item.price_summary}</Text>
              ) : null}
              <Text style={{ color: colors.muted, fontSize: 12 }}>
                {(item.options?.length ?? 0) === 1
                  ? tr('servicesOneOption')
                  : `${item.options?.length ?? 0} ${tr('servicesOptionsLabel')}`}
              </Text>
            </Pressable>
            <Pressable onPress={() => void handleDelete(item.id)} accessibilityRole="button">
              <Text style={{ color: colors.danger }}>{tr('servicesDelete')}</Text>
            </Pressable>
          </View>
        )}
      />
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  loader: { marginVertical: spacing.sm },
  list: { gap: spacing.sm, paddingTop: spacing.md, paddingBottom: spacing.xl },
  empty: { textAlign: 'center', marginTop: spacing.lg, fontFamily: fonts.body },
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  cardMain: { flex: 1, gap: 4 },
  name: { fontFamily: fonts.bodyMedium, fontSize: 16, color: '#10221A' },
});
