# ORCHESTRA DEV

Plateforme locale Windows de pilotage de missions de développement assisté par IA, avec preuves de validation et approbation humaine.

## Objectif V0.1

- Enregistrer des projets locaux et leurs dépôts Git.
- Créer des missions et leurs critères d'acceptation.
- Suivre les transitions d'état avec un journal persistant SQLite.
- Afficher les résultats de vérification sans inventer de preuves.
- Interdire toute publication automatique.

## Architecture cible (à confirmer par prototype)

- Interface React + TypeScript ; conteneur Electron.
- API locale Python/FastAPI ; persistance SQLite.
- Git et worktrees pour isoler les changements.
- Playwright et pytest pour les vérifications.
- Adaptateurs d'agents IA ajoutés en V0.2, après validation des permissions.

## Principes non négociables

1. Pas d'accès arbitraire au système de fichiers : projets autorisés explicitement.
2. Pas de suppression, push, fusion ou déploiement sans approbation humaine.
3. Chaque action et transition est journalisée.
4. Un test non exécuté est `NON_VÉRIFIÉ`, jamais `CONFORME`.
5. Les secrets ne figurent ni dans le dépôt ni dans les rapports.
6. Le développement commence par un prototype fonctionnel et des tests reproductibles.

## États des missions

`CRÉÉE → SPÉCIFIÉE → PLAN_VALIDÉ → EN_EXÉCUTION → EN_VÉRIFICATION → ATTENTE_VALIDATION_HUMAINE → VALIDÉE → PUBLIÉE`.

Transitions d'exception : `BLOQUÉE`, `ANNULÉE`, `ÉCHEC_TECHNIQUE`, `PUBLICATION_ÉCHOUÉE`. Les règles précises de transition seront spécifiées et testées avant leur implémentation.

## Définition de terminé pour V0.1

Une démonstration locale doit permettre de créer un projet, définir une mission, enregistrer des critères d'acceptation, consulter son historique et retrouver les données après redémarrage. Les tests doivent passer et les limitations doivent être documentées.

> Statut : cadrage initial uniquement. Aucune application fonctionnelle n'est encore livrée.
