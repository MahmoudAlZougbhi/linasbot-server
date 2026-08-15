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

/** AI Setup hub — full-width Knowledge/Greetings/Services, then big + two-small mosaic rows. */
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
          return (
            <AiSetupSectionTile
              key={key}
              kind="section"
              tile={row.item.tile}
              variant="full"
              statusBySection={statusBySection}
              onPress={() => onOpenSection(row.item.tile.id)}
            />
          );
        }

        return (
          <AiSetupHubMosaic
            key={`mosaic-${index}`}
            big={row.big}
            smalls={row.smalls}
            statusBySection={statusBySection}
            onOpenSection={onOpenSection}
            onOpenProducts={onOpenProducts}
          />
        );
      })}
    </View>
  );
}
