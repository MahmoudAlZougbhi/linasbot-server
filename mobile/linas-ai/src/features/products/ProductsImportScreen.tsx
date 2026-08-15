import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { pickDocumentAttachment } from '../chat/v2/pickAttachment';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { importProducts, previewProductsImport } from './productsApi';

type Props = {
  onBack: () => void;
  onImported: () => void;
};

export function ProductsImportScreen({ onBack, onImported }: Props) {
  const { tr } = useI18n();
  const [csvText, setCsvText] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [preview, setPreview] = useState<{
    valid_count: number;
    error_count: number;
    preview: { row: number; name: string; valid?: boolean }[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pickFile = async () => {
    setError(null);
    const picked = await pickDocumentAttachment();
    if (!picked) return;
    try {
      const response = await fetch(picked.uri);
      const text = await response.text();
      setCsvText(text);
      setFilename(picked.name);
      setPreview(null);
    } catch {
      setError(tr('productsImportReadError'));
    }
  };

  const runPreview = async () => {
    if (!csvText) {
      setError(tr('productsImportNoFile'));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await previewProductsImport(csvText);
      setPreview(result);
    } catch {
      setError(tr('productsImportPreviewError'));
    } finally {
      setLoading(false);
    }
  };

  const runImport = async () => {
    if (!csvText) {
      setError(tr('productsImportNoFile'));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await importProducts(csvText);
      onImported();
    } catch {
      setError(tr('productsImportError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScreenChrome title={tr('productsImportTitle')} subtitle={tr('productsImportSubtitle')} onBack={onBack}>
      <ScrollView contentContainerStyle={styles.form}>
        <Text style={styles.hint}>{tr('productsImportTemplateHint')}</Text>
        {filename ? <Text style={styles.file}>{filename}</Text> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <PrimaryButton label={tr('productsImportPickFile')} onPress={() => void pickFile()} />
        <PrimaryButton
          label={loading ? tr('productsImportWorking') : tr('productsImportPreview')}
          onPress={() => void runPreview()}
          disabled={!csvText || loading}
        />
        {preview ? (
          <View style={styles.previewBox}>
            <Text style={styles.previewTitle}>
              {tr('productsImportPreviewSummary')
                .replace('{valid}', String(preview.valid_count))
                .replace('{errors}', String(preview.error_count))}
            </Text>
            {preview.preview.slice(0, 12).map((row) => (
              <Text key={`row-${row.row}`} style={row.valid ? styles.rowOk : styles.rowBad}>
                #{row.row}: {row.name || tr('productsImportMissingName')}
              </Text>
            ))}
          </View>
        ) : null}
        <PrimaryButton
          label={tr('productsImportConfirm')}
          onPress={() => void runImport()}
          disabled={!preview || preview.valid_count <= 0 || loading}
        />
      </ScrollView>
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  form: { gap: spacing.md, paddingBottom: spacing.xl },
  hint: { fontFamily: fonts.body, fontSize: 14, color: '#4A5C52' },
  file: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  error: { color: '#C0392B', fontFamily: fonts.body },
  previewBox: { gap: spacing.xs, paddingVertical: spacing.sm },
  previewTitle: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  rowOk: { fontFamily: fonts.body, fontSize: 13 },
  rowBad: { fontFamily: fonts.body, fontSize: 13, color: '#C0392B' },
});
