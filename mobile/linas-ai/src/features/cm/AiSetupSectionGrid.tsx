import { StyleSheet, View } from 'react-native';

import { spacing } from '../../theme';
import { AiSetupSectionTile } from './AiSetupSectionTile';
import type { CmSectionCard } from './cmSections';

type Props = {
  tiles: CmSectionCard[];
  statusBySection: Map<string, 'complete' | 'incomplete'>;
  onOpenSection: (id: CmSectionCard['id']) => void;
};

/** Legacy two-column grid — kept for tests; hub uses AiSetupHubSections. */
export function AiSetupSectionGrid({ tiles, statusBySection, onOpenSection }: Props) {
  return (
    <View style={styles.grid}>
      {tiles.map((tile) => (
        <View key={tile.id} style={styles.cell}>
          <AiSetupSectionTile
            kind="section"
            tile={tile}
            variant="small"
            statusBySection={statusBySection}
            onPress={() => onOpenSection(tile.id)}
          />
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  cell: {
    flexGrow: 1,
    flexBasis: '47%',
    maxWidth: '48%',
  },
});
