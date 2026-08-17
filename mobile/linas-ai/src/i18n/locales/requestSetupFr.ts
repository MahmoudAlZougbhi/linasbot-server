import type { requestSetupEn } from './requestSetupEn';

export const requestSetupFr: Record<keyof typeof requestSetupEn, string> = {
  requestRulesSubtitle: 'Règles pour les rendez-vous, commandes et autres demandes clients.',
  requestRulesAdd: 'Ajouter une règle de demande',
  requestRulesInfoTitle: 'Qu’est-ce qu’une règle de demande ?',
  requestRulesInfoBody:
    'Apprenez à Linas à gérer un rendez-vous, une commande ou une autre demande. Dans la note, indiquez les détails à collecter et les liens à envoyer. Le résultat apparaît dans Demandes.',
  requestRulesSearch: 'Rechercher des règles de demande',
  requestRulesCount: 'règles de demande',
  requestRulesCountOne: 'règle de demande',
  requestRulesFooter: 'Chaque règle utilise la même icône de demande.',
  requestRulesEmpty: 'Aucune règle — appuyez sur Ajouter une règle de demande.',
  requestRulesUntitled: 'Règle sans titre',
  requestRulesPublished: 'Publiée',
  requestRulesDraft: 'Brouillon',
  requestRulesCollects: 'Collecte {fields}',
  requestRulesCollectsEmpty: 'Aucun champ compilé pour l’instant',
  requestRulesEditTitle: 'Modifier la règle de demande',
  requestRulesNote: 'Note pour Linas',
  requestRulesNoteHint: 'Indiquez les détails à collecter et les liens à envoyer.',
  requestRulesSave: 'Enregistrer',
  requestRulesNameRequired: 'Entrez un titre.',
  requestRulesDeleteTitle: 'Supprimer cette règle de demande ?',
  requestRulesDeleteBody: 'Cette règle sera retirée de Configuration IA.',
  requestRulesPreviewFailed: 'Impossible de prévisualiser ce graphe de demande.',
  requestRulesPublishFailed: 'Brouillon enregistré, mais la publication du graphe a échoué.',
  requestRulesGraphLoadFailed: 'Impossible de charger les graphes de demande publiés.',
  requestRulesGraphUnmigrated:
    'Les tables de graphes de demande ne sont pas encore migrées sur ce serveur. Les règles restent en brouillon.',
  requestRulesGraphDbUnavailable: 'Base client indisponible pour les graphes de demande.',
  requestRulesDeleteGraphFailed:
    'Règle retirée du brouillon, mais le graphe publié n’a pas pu être supprimé.',
};
