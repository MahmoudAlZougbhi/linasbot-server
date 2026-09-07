import { ScrollView, StyleSheet } from 'react-native';

import type { StringKey } from '../../../i18n';
import { CommentListView } from './CommentListView';
import type { CommentRuleItem } from './commentModel';

type Props = {
  items: CommentRuleItem[];
  query: string;
  onQueryChange: (value: string) => void;
  onAdd: () => void;
  onSelect: (id: string) => void;
  tr: (key: StringKey) => string;
};

export function CommentsListPanel({ items, query, onQueryChange, onAdd, onSelect, tr }: Props) {
  return (
    <ScrollView contentContainerStyle={styles.listScroll} showsVerticalScrollIndicator={false}>
      <CommentListView
        items={items}
        query={query}
        onQueryChange={onQueryChange}
        onAdd={onAdd}
        onSelect={onSelect}
        tr={tr}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  listScroll: { flexGrow: 1, paddingBottom: 16 },
});
