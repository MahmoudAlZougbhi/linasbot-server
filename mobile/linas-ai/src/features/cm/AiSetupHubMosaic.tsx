import { StyleSheet, View } from 'react-native';

import { spacing } from '../../theme';
import { AiSetupSectionTile } from './AiSetupSectionTile';
import type { HubItem } from './aiSetupHubLayout';
import type { CmSectionCard } from './cmSections';

type Props = {
  left: HubItem;
  right: HubItem;
  statusBySection: Map<string, 'complete' | 'incomplete'>;
  onOpenSection: (id: CmSectionCard['id']) => void;
  onOpenProducts?: () => void;
};

function renderItem(
  item: HubItem,
  statusBySection: Map<string, 'complete' | 'incomplete'>,
  onOpenSection: (id: CmSectionCard['id']) => void,
  onOpenProducts?: () => void,
) {
  if (item.kind === 'products') {
    if (!onOpenProducts) return null;
    return <AiSetupSectionTile kind="products" variant="big" onPress={onOpenProducts} />;
  }
  return (
    <AiSetupSectionTile
      kind="section"
      tile={item.tile}
      variant="big"
      statusBySection={statusBySection}
      onPress={() => onOpenSection(item.tile.id)}
    />
  );
}

/** Two equal tiles side by side — hub pair mosaic row. */
export function AiSetupHubMosaic({ left, right, statusBySection, onOpenSection, onOpenProducts }: Props) {
  return (
    <View style={styles.row}>
      <View style={styles.cell}>{renderItem(left, statusBySection, onOpenSection, onOpenProducts)}</View>
      <View style={styles.cell}>{renderItem(right, statusBySection, onOpenSection, onOpenProducts)}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: spacing.sm, alignItems: 'stretch' },
  cell: { flex: 1 },
});
