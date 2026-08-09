/** Approved Linas PNG states cropped from the brand sheet (not new faces). */
export type LinasAvatarState =
  | 'idle'
  | 'welcome'
  | 'listening'
  | 'thinking'
  | 'typing'
  | 'success'
  | 'error'
  | 'happy'
  | 'excited'
  | 'helping'
  | 'winking'
  | 'thank_you';

const portrait = require('../../../assets/linas-avatar-chat.png');
const emptyState = require('../../../assets/linas-empty-state.png');
const authHero = require('../../../assets/linas-auth-hero.png');

const states = {
  idle: require('../../../assets/linas-state-idle.png'),
  welcome: require('../../../assets/linas-state-welcome.png'),
  listening: require('../../../assets/linas-state-listening.png'),
  thinking: require('../../../assets/linas-state-thinking.png'),
  typing: require('../../../assets/linas-state-typing.png'),
  success: require('../../../assets/linas-state-success.png'),
  error: require('../../../assets/linas-state-error.png'),
  happy: require('../../../assets/linas-expr-happy.png'),
  excited: require('../../../assets/linas-expr-excited.png'),
  helping: require('../../../assets/linas-expr-helping.png'),
  winking: require('../../../assets/linas-expr-winking.png'),
  thank_you: require('../../../assets/linas-expr-thank_you.png'),
} as const;

export const linasAssets = {
  portrait,
  emptyState,
  authHero,
  icon: require('../../../assets/icon.png'),
  splashIcon: require('../../../assets/splash-icon.png'),
  states,
} as const;

export function avatarSourceForState(state: LinasAvatarState) {
  return states[state] ?? states.idle;
}
