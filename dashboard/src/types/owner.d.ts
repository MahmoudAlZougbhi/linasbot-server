interface OwnerAnalytics {
  new_users: number;
  live_users: number;
  subscribers: number;
  comments: number;
  credits_total: number;
  credits_used: number;
  credits_remaining: number;
  intended_message_mrr_usd?: number;
  live_checkout_mrr_usd?: number;
  messages_by_channel: Record<string, number>;
  coverage: Record<string, string>;
}

interface OwnerSubscriber {
  tenant_id: string;
  email?: string;
  business_name?: string;
  subscription: string;
  membership: string;
  seats_created: number;
  roles: string[];
  status: string;
  credits_used: number;
  credits_remaining: number;
  intended_included_messages?: number | null;
  intended_price_usd?: number | null;
  users: DashboardUser[];
}

interface OwnerInteractionLog {
  timestamp?: string;
  message_id?: string;
  channel?: string;
  source?: string;
  user_message?: string;
  bot_to_user?: string;
  faq_match?: { faq_id?: string };
}
