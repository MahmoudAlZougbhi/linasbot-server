import { View } from 'react-native';

import { spacing } from '../../theme';
import { AiSetupHubMosaic } from './AiSetupHubMosaic';
import { AiSetupSectionTile } from './AiSetupSectionTile';
import { buildAiSetupHubRows } from './aiSetupHubLayout';
import type { CmSectionCard } from './cmSections';

type Props = {
  tiles: CmSectionCard[];
  statusBySection: Map<string, 'complete' | 'incomplete'>;
  onOpenSection: (id: CmSectionCard['id']) => void;
  onOpenProducts?: () => void;
};

/** AI Setup hub — full-width AI Basics + Knowledge, then pair mosaic rows. */
export function AiSetupHubSections({ tiles, statusBySection, onOpenSection, onOpenProducts }: Props) {
  const rows = buildAiSetupHubRows(tiles, Boolean(onOpenProducts));

  return (
    <View style={{ gap: spacing.sm }}>
      {rows.map((row, index) => {
        if (row.type === 'full') {
          const key = row.item.kind === 'products' ? 'products-full' : row.item.tile.id;
          if (row.item.kind === 'products') {
            if (!onOpenProducts) return null;
            return (
              <AiSetupSectionTile
                key={key}
                kind="products"
                variant="full"
                onPress={onOpenProducts}
              />
            );
          }
          const { tile } = row.item;
          return (
            <AiSetupSectionTile
              key={tile.id}
              kind="section"
              tile={tile}
              variant="full"
              statusBySection={statusBySection}
              onPress={() => onOpenSection(tile.id)}
            />
          );
        }

        return (
          <AiSetupHubMosaic
            key={`pair-${index}`}
            left={row.left}
            right={row.right}
            statusBySection={statusBySection}
            onOpenSection={onOpenSection}
            onOpenProducts={onOpenProducts}
          />
        );
      })}
    </View>
  );
}
