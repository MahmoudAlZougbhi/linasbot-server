/**
 * Push scaffolding for Linas AI owner alerts.
 *
 * Does NOT enable Expo/FCM/APNs delivery. No google-services / APNs secrets.
 * Call after login once Mahmoud approves push infra; until then this is a no-op
 * that documents the approval gate.
 */
export const PUSH_INFRA_STATUS = 'pending_mahmoud_approval' as const;

export async function tryRegisterOwnerPushScaffold(_opts?: {
  enabled?: boolean;
}): Promise<{ status: typeof PUSH_INFRA_STATUS; reason: string }> {
  return {
    status: PUSH_INFRA_STATUS,
    reason:
      'expo-notifications / FCM / APNs not configured for Linas AI. In-app inbox works; ask Mahmoud before adding push credentials.',
  };
}
