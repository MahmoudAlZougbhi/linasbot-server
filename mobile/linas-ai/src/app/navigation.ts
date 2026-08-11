import type { CmProposalReview } from '../features/cm/cmProposalReview';
import type { CmSectionId } from '../features/cm/cmSections';
import type { ControlArea } from '../features/control/controlAreas';

export type LiveChatOpen = { userId: string; conversationId: string };

export type Screen =
  | { name: 'boot' }
  | { name: 'login' }
  | { name: 'register' }
  | { name: 'chat' }
  | { name: 'settings' }
  | { name: 'integrations' }
  | { name: 'users' }
  | { name: 'dashboard' }
  | { name: 'billing' }
  | { name: 'livechat'; open?: LiveChatOpen | null }
  | { name: 'notifications'; backTo?: 'chat' | 'settings' }
  | { name: 'cm' }
  | {
      name: 'cm_section';
      section: CmSectionId;
      backTo?: 'cm' | 'settings' | 'chat';
      proposalReview?: CmProposalReview | null;
    }
  | { name: 'faq'; proposalReview?: CmProposalReview | null }
  | { name: 'resource'; title: string; path: string };

export const RESOURCE_MAP: Partial<Record<ControlArea, { title: string; path: string }>> = {
  owner: { title: 'Owner Control Center', path: '/api/platform/metrics' },
};

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

export type IntegrationsDeepLink = {
  metaConnection: 'success' | 'cancelled' | 'failed' | null;
};

export function parseIntegrationsDeepLink(url: string | null): IntegrationsDeepLink | null {
  if (!url) return null;
  try {
    const normalized = url.replace(/^linasai:\/\//i, 'https://linasai.app/');
    const parsed = new URL(normalized);
    const path = parsed.pathname.replace(/^\//, '');
    if (path !== 'integrations' && !path.startsWith('integrations/')) {
      return null;
    }
    const raw = (parsed.searchParams.get('meta_connection') || '').trim().toLowerCase();
    if (raw === 'success' || raw === 'connected') {
      return { metaConnection: 'success' };
    }
    if (raw === 'cancelled' || raw === 'canceled') {
      return { metaConnection: 'cancelled' };
    }
    if (raw === 'failed') {
      return { metaConnection: 'failed' };
    }
    return { metaConnection: null };
  } catch {
    return null;
  }
}
