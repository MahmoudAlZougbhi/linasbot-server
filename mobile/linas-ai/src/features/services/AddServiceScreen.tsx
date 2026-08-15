import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { Field } from '../cm/editors/Field';
import { ScreenChrome } from '../shared/ScreenChrome';
import { ServiceOptionRow } from './ServiceOptionRow';
import {
  createService,
  emptyOptionRow,
  fetchService,
  updateService,
  type ServiceOptionInput,
  type ServiceWriteInput,
} from './servicesApi';

type Props = {
  serviceId?: string | null;
  onBack: () => void;
  onSaved: () => void;
};

export function AddServiceScreen({ serviceId, onBack, onSaved }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const editing = Boolean(serviceId);
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [options, setOptions] = useState<ServiceOptionInput[]>([emptyOptionRow()]);

  useEffect(() => {
    if (!serviceId) return;
    void (async () => {
      setLoading(true);
      try {
        const service = await fetchService(serviceId);
        setName(service.name);
        setOptions(
          (service.options ?? []).length
            ? (service.options ?? []).map((opt) => ({
                id: opt.id,
                machine_name: opt.machine_name ?? '',
                body_part: opt.body_part ?? '',
                staff_name: opt.staff_name ?? '',
                price: opt.price,
                currency: opt.currency ?? 'USD',
                sort_order: opt.sort_order,
              }))
            : [emptyOptionRow()],
        );
      } catch {
        setError(tr('servicesLoadError'));
      } finally {
        setLoading(false);
      }
    })();
  }, [serviceId, tr]);

  const patchOption = (index: number, next: ServiceOptionInput) => {
    setOptions((rows) => rows.map((row, i) => (i === index ? next : row)));
  };

  const buildPayload = (): ServiceWriteInput => ({
    name: name.trim(),
    active: true,
    options: options.map((row, index) => ({
      id: row.id,
      machine_name: row.machine_name?.trim() || null,
      body_part: row.body_part?.trim() || null,
      staff_name: row.staff_name?.trim() || null,
      price: row.price.trim(),
      currency: row.currency?.trim() || 'USD',
      sort_order: index,
    })),
  });

  const save = async () => {
    if (!name.trim()) {
      setError(tr('servicesNameRequired'));
      return;
    }
    const priced = options.filter((row) => row.price.trim());
    if (!priced.length) {
      setError(tr('servicesPriceRequired'));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = { ...buildPayload(), options: priced };
      if (editing && serviceId) {
        await updateService(serviceId, payload);
      } else {
        await createService(payload);
      }
      onSaved();
    } catch {
      setError(tr('servicesSaveError'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <ScreenChrome
        title={tr(editing ? 'servicesEditTitle' : 'servicesAddTitle')}
        onBack={onBack}
      >
        <LinasLoadingIndicator variant="screen" />
      </ScreenChrome>
    );
  }

  return (
    <ScreenChrome
      title={tr(editing ? 'servicesEditTitle' : 'servicesAddTitle')}
      onBack={onBack}
    >
      <ScrollView contentContainerStyle={styles.form} keyboardShouldPersistTaps="handled">
        {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
        <Field label={tr('servicesName')} value={name} onChange={setName} />

        <Text style={styles.section}>{tr('servicesOptionsSection')}</Text>
        {options.map((option, index) => (
          <ServiceOptionRow
            key={`opt-${index}`}
            index={index}
            option={option}
            canRemove={options.length > 1}
            onChange={(next) => patchOption(index, next)}
            onRemove={() => setOptions((rows) => rows.filter((_, i) => i !== index))}
          />
        ))}

        <Pressable
          onPress={() => setOptions((rows) => [...rows, emptyOptionRow()])}
          style={styles.addOption}
        >
          <Text style={{ color: colors.accent }}>{tr('servicesAddOption')}</Text>
        </Pressable>

        <PrimaryButton
          label={saving ? tr('servicesSaving') : tr('servicesSave')}
          onPress={() => void save()}
          disabled={saving}
        />
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  form: { gap: spacing.md, paddingBottom: spacing.xl },
  section: {
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    color: '#10221A',
    marginTop: spacing.sm,
  },
  addOption: { paddingVertical: spacing.xs },
});
