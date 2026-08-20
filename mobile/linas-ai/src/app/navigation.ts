import type { CmProposalReview } from '../features/cm/cmProposalReview';
import type { CmSectionId } from '../features/cm/cmSections';
import type { ControlArea } from '../features/control/controlAreas';

export type LiveChatOpen = { userId: string; conversationId: string };

export type Screen =
  | { name: 'boot' }
  | { name: 'login' }
  | { name: 'register' }
  | { name: 'forgot_password' }
  | { name: 'chat' }
  | { name: 'settings' }
  | { name: 'integrations' }
  | { name: 'users' }
  | { name: 'dashboard' }
  | { name: 'billing'; browsePlans?: boolean }
  | { name: 'livechat'; open?: LiveChatOpen | null }
  | { name: 'requests' }
  | { name: 'notifications'; backTo?: 'chat' | 'settings' }
  | { name: 'cm' }
  | { name: 'products'; backTo?: 'cm' }
  | { name: 'products_import'; backTo?: 'products' }
  | { name: 'products_add'; backTo?: 'products' }
  | { name: 'products_details'; productId: string; backTo?: 'products' }
  | { name: 'products_edit'; productId: string; backTo?: 'products' | 'products_details' }
  | { name: 'services'; backTo?: 'cm' | 'chat'; proposalReview?: CmProposalReview | null }
  | {
      name: 'cm_section';
      section: CmSectionId;
      backTo?: 'cm' | 'settings' | 'chat';
      proposalReview?: CmProposalReview | null;
    }
  | { name: 'faq'; proposalReview?: CmProposalReview | null }
  | { name: 'smartFollowUp' }
  | { name: 'owner' }
  | { name: 'resource'; title: string; path: string };

export const RESOURCE_MAP: Partial<Record<ControlArea, { title: string; path: string }>> = {};

export function parseLiveChatDeepLink(url: string | null): LiveChatOpen | null {
  if (!url) return null;
  try {
    const normalized = url.replace(/^linasai:\/\//i, 'https://linasai.app/');
    const parsed = new URL(normalized);
    const path = parsed.pathname.replace(/^\//, '');
    if (path !== 'livechat' && !path.startsWith('livechat/')) {
      return null;
    }
    const userId = parsed.searchParams.get('userId') || parsed.searchParams.get('user_id');
    const conversationId =
      parsed.searchParams.get('conversationId') || parsed.searchParams.get('conversation_id');
    if (userId && conversationId) {
      return { userId, conversationId };
    }
    const parts = path.split('/').filter(Boolean);
    if (parts.length >= 3 && parts[0] === 'livechat') {
      return { userId: decodeURIComponent(parts[1]), conversationId: decodeURIComponent(parts[2]) };
    }
  } catch {
    return null;
  }
  return null;
}

export type { IntegrationsDeepLink } from './integrationsDeepLink';
export { parseIntegrationsDeepLink } from './integrationsDeepLink';
