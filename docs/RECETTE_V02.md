# Recette automatisée V0.2

## Objectif

Exécuter les six tests unitaires Python et deux scénarios navigateur Playwright Chromium sur un serveur local temporaire. Les scénarios vérifient les créations de projet, mission, critère, génération de consigne, persistance après rechargement et affichage mobile.

## Sur GitHub

Ouvrir **Actions** > **V0.2 acceptance** > dernier run. Attendre le résultat vert avant de considérer la recette validée. Ouvrir **Artifacts** > `orchestra-v02-evidence` pour consulter les rapports et captures. Les preuves ne sont conservées que 14 jours.

## Sur Windows

Dans le dépôt :

```powershell
git pull
python -m unittest discover -s tests -v
npm install
npx playwright install chromium
npm run test:e2e
```

Le test navigateur lance son propre serveur sur le port 8766. Arrêter auparavant tout serveur local ORCHESTRA DEV utilisant ce port. La base E2E est séparée de la base utilisateur.

## Interprétation

- **Vert** : les scénarios exécutés ont réussi, pas une garantie générale d'absence de défauts.
- **Rouge** : consulter les traces, corriger et relancer.
- **Absent/en attente** : ne pas annoncer la réussite.

## Limites

La recette ne teste pas encore Electron, les agents IA réels, les permissions système, l'isolation des worktrees, les navigateurs Firefox/WebKit, ni la qualité graphique de référence. La capture est une preuve de rendu, pas une évaluation artistique. La V0.2 actuelle est une préparation manuelle de consignes Codex, pas un connecteur Codex autonome.
