import FeatureCarousel from '../FeatureCarousel';
import {
  ReplyChannels,
  ReplyComments,
  ReplyCustomer,
  ReplyLanguage,
  ReplyOneInbox,
  ReplyVoiceVision,
} from '../cards/ReplyMinis';

const CARDS = [
  {
    id: 'replies',
    title: 'AI Customer Replies',
    description: 'Handles hard questions from your knowledge — not just simple ones.',
    Mini: ReplyCustomer,
  },
  {
    id: 'language',
    title: 'Any Language',
    description: 'Understands and replies in every language customers actually write in.',
    Mini: ReplyLanguage,
  },
  {
    id: 'one-inbox',
    title: 'One place for every chat',
    description: 'Manage all customer chats from one inbox — every channel, one view.',
    core: true,
    Mini: ReplyOneInbox,
  },
  {
    id: 'comments',
    title: 'Comments + Private DM',
    description: 'Teach how Linas should handle each comment — public reply, private DM, or both.',
    Mini: ReplyComments,
  },
  {
    id: 'voice',
    title: 'Voice & Vision',
    description: 'Listens to voice notes and understands customer images.',
    Mini: ReplyVoiceVision,
  },
  {
    id: 'channels',
    title: 'Every Channel',
    description: 'Connect Instagram, Facebook, WhatsApp, TikTok and Web Chat.',
    Mini: ReplyChannels,
  },
];

export default function LandingReply() {
  return (
    <FeatureCarousel
      id="reply"
      kicker="Reply"
      title="Every customer gets the"
      accent="right answer."
      subtitle="Messages, comments, voice and images — across every language and channel."
      cards={CARDS}
    />
  );
}
