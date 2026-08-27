import FeatureCarousel from '../FeatureCarousel';
import { ControlAssignment, ControlHandoff, ControlLimits, ControlLiveChat, ControlRoles } from '../cards/ControlMinis';

const CARDS = [
  {
    id: 'handoff',
    title: 'Smart Handoff',
    description: 'Detects when a customer asks for a person, feels frustrated or needs help.',
    Mini: ControlHandoff,
  },
  {
    id: 'roles',
    title: 'Team Roles',
    description: 'Give each teammate only the access they need.',
    Mini: ControlRoles,
  },
  {
    id: 'live-chat',
    title: 'Unified Live Chat',
    description: 'Manage all chats from one place — take over, assign, and keep full context.',
    core: true,
    Mini: ControlLiveChat,
  },
  {
    id: 'assign',
    title: 'Smart Assignment',
    description: 'Assign chats and requests to the right team member.',
    Mini: ControlAssignment,
  },
  {
    id: 'limits',
    title: 'AI Limits',
    description: 'Set safe limits per customer, message and time period.',
    Mini: ControlLimits,
  },
];

export default function LandingControl() {
  return (
    <FeatureCarousel
      id="control"
      kicker="Control"
      title="Stay in control of every"
      accent="conversation."
      subtitle="Take over, assign work and protect your credits without losing context."
      cards={CARDS}
    />
  );
}
