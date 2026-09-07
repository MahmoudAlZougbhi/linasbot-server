import { Image, Pressable, StyleSheet, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { CommentChannelIcon } from '../../livechat/comments/CommentsPlatformChips';
import { CM_BORDER, CM_RADIUS_SM, CM_TEAL_SOFT } from './commentChrome';
import type { SelectedCommentPost } from './commentPostSnapshots';

type Props = {
  posts: SelectedCommentPost[];
  onPress: () => void;
};

export function CommentSelectedPosts({ posts, onPress }: Props) {
  if (!posts.length) return null;
  return (
    <View style={styles.wrap}>
      {posts.map((post) => (
        <Pressable
          key={`${post.platform}:${post.id}`}
          onPress={onPress}
          accessibilityRole="button"
          style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
        >
          {post.thumbnail ? (
            <Image source={{ uri: post.thumbnail }} style={styles.image} />
          ) : (
            <View style={styles.fallback}>
              <AppIcon icon={feather('image')} size={18} color="#107C75" />
            </View>
          )}
          <View style={styles.badge}>
            <CommentChannelIcon platform={post.platform} size={14} />
          </View>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  tile: {
    width: 72,
    height: 72,
    borderRadius: CM_RADIUS_SM,
    overflow: 'hidden',
    backgroundColor: CM_TEAL_SOFT,
    borderWidth: 1,
    borderColor: CM_BORDER,
  },
  image: { width: '100%', height: '100%' },
  fallback: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  badge: {
    position: 'absolute',
    right: 4,
    bottom: 4,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.7 },
});
