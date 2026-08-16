import FeatureCarousel from '../FeatureCarousel';
import { ReplyChannels, ReplyComments, ReplyCustomer, ReplyLanguage, ReplyVoiceVision } from '../cards/ReplyMinis';

const CARDS = [
  {
    id: 'replies',
    title: 'AI Customer Replies',
    description: 'Answers messages using your saved business knowledge.',
    Mini: ReplyCustomer,
  },
  {
    id: 'language',
    title: 'Any Language',
    description: "Understands and replies in the customer's language.",
    Mini: ReplyLanguage,
  },
  {
    id: 'comments',
    title: 'Comments + Private DM',
    description: 'Replies publicly, then continues privately when details are needed.',
    core: true,
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
