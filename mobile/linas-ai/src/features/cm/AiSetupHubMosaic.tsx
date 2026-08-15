import { StyleSheet, View } from 'react-native';

import { spacing } from '../../theme';
import { AiSetupSectionTile } from './AiSetupSectionTile';
import type { HubItem } from './aiSetupHubLayout';
import type { CmSectionCard } from './cmSections';

type Props = {
  big: HubItem;
  smalls: HubItem[];
  statusBySection: Map<string, 'complete' | 'incomplete'>;
  onOpenSection: (id: CmSectionCard['id']) => void;
  onOpenProducts?: () => void;
};

function renderItem(
  item: HubItem,
  variant: 'big' | 'small',
  statusBySection: Map<string, 'complete' | 'incomplete'>,
  onOpenSection: (id: CmSectionCard['id']) => void,
  onOpenProducts?: () => void,
) {
  if (item.kind === 'products') {
    if (!onOpenProducts) return null;
    return <AiSetupSectionTile kind="products" variant={variant} onPress={onOpenProducts} />;
  }
  return (
    <AiSetupSectionTile
      kind="section"
      tile={item.tile}
      variant={variant}
      statusBySection={statusBySection}
      onPress={() => onOpenSection(item.tile.id)}
    />
  );
}

/** One large tile with up to two stacked small tiles — alternating hub mosaic row. */
export function AiSetupHubMosaic({ big, smalls, statusBySection, onOpenSection, onOpenProducts }: Props) {
  return (
    <View style={styles.row}>
      {renderItem(big, 'big', statusBySection, onOpenSection, onOpenProducts)}
      {smalls.length > 0 ? (
        <View style={styles.smallColumn}>
          {smalls.map((item, index) => (
            <View key={item.kind === 'products' ? 'products' : item.tile.id} style={index > 0 ? styles.smallGap : undefined}>
              {renderItem(item, 'small', statusBySection, onOpenSection, onOpenProducts)}
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: spacing.sm, alignItems: 'stretch' },
  smallColumn: { flex: 1, justifyContent: 'space-between' },
  smallGap: { marginTop: spacing.sm },
});
