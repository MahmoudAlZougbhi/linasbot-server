/** Integrations account display + app version gate copy (fr). */
export const integrationsDisplayFr = {
  metaOAuthFailedFacebook:
    'Échec de l’autorisation Facebook. Appuyez sur Connecter pour réessayer.',
  metaOAuthFailedFacebookScopes:
    'Facebook n’a pas accordé toutes les autorisations requises, y compris business_management. Accordez à ce compte l’accès à la Page, acceptez chaque autorisation demandée, puis appuyez sur Connecter.',
  metaOAuthFailedFacebookToken:
    'Meta a rejeté le code d’autorisation Facebook. Reconnectez Facebook.',
  metaOAuthFailedFacebookWebhook:
    'Facebook est connecté, mais la configuration webhook n’a pas abouti. Reconnectez Facebook dans une minute.',
  metaOAuthFailedFacebookDeletion:
    'L’autorisation Facebook est bloquée par une demande de suppression Meta en attente.',
  metaOAuthFailedFacebookDeletionFailed:
    'L’autorisation Facebook est bloquée car une demande de suppression Meta a échoué. Demandez à un administrateur de la résoudre, puis reconnectez Facebook.',
  metaOAuthFailedFacebookBusy:
    'Une autre connexion Facebook est en cours. Patientez un instant, puis appuyez une fois sur Connecter.',
  metaOAuthFailedFacebookGuard:
    'La connexion Facebook n’a pas pu vérifier son état de sécurité. Patientez, puis réessayez.',
  metaOAuthFailedFacebookConfig:
    'Facebook Login n’est pas encore prêt sur le serveur. Réessayez après la dernière mise à jour.',
  metaOAuthFailedFacebookConflict:
    'Cette Page Facebook est déjà connectée à un autre espace de travail.',
  metaOAuthFailedFacebookNoPage:
    'Aucune Page Facebook éligible n’est disponible. Accordez à ce compte l’accès aux messages et à l’activité communautaire de la Page (ou le contrôle total), puis appuyez sur Connecter.',
  metaOAuthFailedBusy:
    'Une autre connexion Instagram est en cours. Patientez un instant, puis appuyez une fois sur Connecter.',
  metaOAuthFailedGuard:
    'La connexion Instagram n’a pas pu vérifier son état de sécurité. Patientez, puis réessayez.',
  metaOAuthFailedDeletionFailed:
    'L’autorisation Instagram est bloquée car une demande de suppression Meta a échoué. Demandez à un administrateur de la résoudre, puis reconnectez Instagram.',
  metaOAuthFailedProvider:
    'Meta ne peut pas terminer la configuration Instagram pour le moment. Attendez cinq minutes, puis appuyez une fois sur Connecter.',
  integrationStatusConnected: 'Connexion saine',
  integrationStatusNeedsReconnect: 'Reconnexion requise',
  integrationStatusError: 'Problème de connexion',
  integrationLastSynced: 'Dernière synchro',
  integrationReconnect: 'Reconnecter',
  integrationConnectedFeatures: 'Fonctionnalités connectées',
  integrationMessengerReplies: 'Réponses Messenger',
  integrationDmReplies: 'Réponses DM',
  integrationCommentReplies: 'Réponses aux commentaires',
  integrationFeatureOn: 'Activé',
  integrationFeatureOff: 'Désactivé',
  integrationToggleMessages: 'Messages',
  integrationRefreshStatus: 'Actualiser le statut',
  integrationDisconnectAccount: 'Déconnecter le compte',
  integrationDisconnectHint: 'Les réponses IA s’arrêtent jusqu’à la reconnexion.',
  integrationWhatsAppHandle: 'Numéro professionnel',
  integrationStatusConnecting: 'Connexion…',
  integrationStatusPermissionRequired: 'Permission requise',
  integrationStatusTokenExpired: 'Jeton expiré',
  tiktokMessagingPending: 'Les DM TikTok sont en attente de l’approbation Business Messaging.',
  tiktokLastSyncNever: 'Pas encore synchronisé',
  drawerRecents: 'Récents',
  drawerPin: 'Épinglés',
  appUpdateForceTitle: 'Mise à jour requise',
  appUpdateForceBody:
    'Cette version ({min}) n’est plus prise en charge. Installez {latest} ou plus récent pour continuer.',
  appUpdateAvailableTitle: 'Mise à jour disponible',
  appUpdateAvailableBody: 'La version {latest} est disponible sur l’App Store / Play Store.',
  appUpdateOpenStore: 'Mettre à jour',
  appUpdateDismiss: 'Plus tard',
} as const;
