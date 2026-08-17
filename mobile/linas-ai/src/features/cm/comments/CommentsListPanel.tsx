import { ScrollView, StyleSheet } from 'react-native';

import type { StringKey } from '../../../i18n';
import { CommentInboxView } from './CommentInboxView';
import { CommentListView } from './CommentListView';
import { CommentSegmented } from './CommentSegmented';
import type { CommentRuleItem } from './commentModel';

type ListTab = 'rules' | 'inbox';

type Props = {
  listTab: ListTab;
  onChangeTab: (tab: ListTab) => void;
  items: CommentRuleItem[];
  query: string;
  onQueryChange: (value: string) => void;
  onAdd: () => void;
  onSelect: (id: string) => void;
  tr: (key: StringKey) => string;
};

export function CommentsListPanel({
  listTab,
  onChangeTab,
  items,
  query,
  onQueryChange,
  onAdd,
  onSelect,
  tr,
}: Props) {
  return (
    <ScrollView contentContainerStyle={styles.listScroll} showsVerticalScrollIndicator={false}>
      <CommentSegmented
        label={tr('aiSetupSec_comments')}
        value={listTab}
        options={[
          { id: 'rules', label: tr('commentsRulesTab') },
          { id: 'inbox', label: tr('commentsInboxTab') },
        ]}
        onChange={onChangeTab}
      />
      {listTab === 'inbox' ? <CommentInboxView tr={tr} /> : null}
      {listTab === 'rules' ? (
        <CommentListView
          items={items}
          query={query}
          onQueryChange={onQueryChange}
          onAdd={onAdd}
          onSelect={onSelect}
          tr={tr}
        />
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  listScroll: { flexGrow: 1, paddingBottom: 16 },
});
