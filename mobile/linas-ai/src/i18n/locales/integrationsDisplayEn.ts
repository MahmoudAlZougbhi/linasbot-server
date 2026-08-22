/** Integrations account display + app version gate copy (en). */
export const integrationsDisplayEn = {
  metaOAuthFailedFacebook: 'Facebook authorization failed. Tap Connect to try again.',
  metaOAuthFailedFacebookScopes:
    'Facebook did not grant all required permissions, including business_management. Give this Facebook account Page access, allow every requested permission, then tap Connect again.',
  metaOAuthFailedFacebookToken:
    'Meta rejected the Facebook authorization code. Connect Facebook again.',
  metaOAuthFailedFacebookWebhook:
    'Facebook connected, but webhook setup did not finish. Connect Facebook again in one minute.',
  metaOAuthFailedFacebookDeletion:
    'Facebook authorization is blocked by a pending Meta data-deletion request.',
  metaOAuthFailedFacebookDeletionFailed:
    'Facebook authorization is blocked because a Meta data-deletion request failed. Ask an administrator to resolve it, then Connect again.',
  metaOAuthFailedFacebookBusy:
    'Another Facebook connection is still finishing. Wait a moment, then tap Connect once.',
  metaOAuthFailedFacebookGuard:
    'Facebook connection could not verify its safety state. Wait a moment, then try again.',
  metaOAuthFailedFacebookConfig:
    'Facebook Login is not ready on the server yet. Try again after the latest server update.',
  metaOAuthFailedFacebookConflict:
    'This Facebook Page is already connected to another workspace.',
  metaOAuthFailedFacebookNoPage:
    'No eligible Facebook Page was available. Give this Facebook account Page access for Messages and community activity (or full control), then tap Connect again.',
  metaOAuthFailedBusy:
    'Another Instagram connection is still finishing. Wait a moment, then tap Connect once.',
  metaOAuthFailedGuard:
    'Instagram connection could not verify its safety state. Wait a moment, then try again.',
  metaOAuthFailedDeletionFailed:
    'Instagram authorization is blocked because a Meta data-deletion request failed. Ask an administrator to resolve it, then Connect again.',
  metaOAuthFailedProvider:
    'Meta could not finish the Instagram setup right now. Wait five minutes, then tap Connect once.',
  integrationStatusConnected: 'Connection healthy',
  integrationStatusNeedsReconnect: 'Needs reconnect',
  integrationStatusError: 'Connection issue',
  integrationLastSynced: 'Last synced',
  integrationReconnect: 'Reconnect',
  integrationConnectedFeatures: 'Connected features',
  integrationMessengerReplies: 'Messenger replies',
  integrationDmReplies: 'DM replies',
  integrationCommentReplies: 'Comment replies',
  integrationFeatureOn: 'On',
  integrationFeatureOff: 'Off',
  integrationToggleMessages: 'Messages',
  integrationRefreshStatus: 'Refresh status',
  integrationDisconnectAccount: 'Disconnect account',
  integrationDisconnectHint: 'AI replies stop until you reconnect.',
  integrationWhatsAppHandle: 'Business number',
  integrationStatusConnecting: 'Connecting',
  integrationStatusPermissionRequired: 'Permission required',
  integrationStatusTokenExpired: 'Token expired',
  tiktokMessagingPending: 'TikTok DMs are pending TikTok Business Messaging approval.',
  tiktokLastSyncNever: 'Not synced yet',
  drawerRecents: 'Recents',
  drawerPin: 'Pin',
  appUpdateForceTitle: 'Update required',
  appUpdateForceBody:
    'This version ({min}) is no longer supported. Install {latest} or newer to continue using Linas AI.',
  appUpdateAvailableTitle: 'Update available',
  appUpdateAvailableBody: 'Version {latest} is available on the App Store / Play Store.',
  appUpdateOpenStore: 'Update in store',
  appUpdateDismiss: 'Not now',
} as const;
