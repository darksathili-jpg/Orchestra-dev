# ORCHESTRA DEV V0.3 — première tranche : Architecte local

Cette tranche fournit un pont **en ligne de commande** vers Codex CLI pour produire un plan **en lecture seule**. Elle ne connecte pas encore le tableau de bord au processus Codex, n'exécute aucun agent Développeur ou Vérificateur et n'effectue aucun commit, merge ou push.

## Prérequis

- Python 3.12+ et Git
- Codex CLI installé, disponible dans PATH et authentifié par l'utilisateur
- Un dépôt Git **local** déjà cloné

## Vérifier la configuration

```powershell
python -m orchestra.agent_cli doctor
```

## Préparer une mission

Dans le tableau de bord, générer et copier la consigne d'une mission. L'enregistrer dans un fichier UTF-8 `mission.txt` (dans un emplacement de votre choix).

## Demander un plan à Codex

```powershell
python -m orchestra.agent_cli plan --workspace "C:\\chemin\\vers\\depot" --brief-file "C:\\chemin\\vers\\mission.txt"
```

Le pont utilise `codex exec --sandbox read-only --cd <workspace> -- <prompt>` et affiche le résultat JSON. La durée limite est de 180 secondes. Le processus ne reçoit pas de shell et ne peut pas modifier le dépôt via les permissions du bac à sable Codex. Les capacités réelles du bac à sable dépendent de l'installation de Codex et du système d'exploitation : vérifier son comportement sur Windows avant de lui confier des données sensibles.

## Limites et règles

- Le mode lecture seule ne garantit pas que Codex ne puisse lire aucune donnée sensible accessible dans le dossier : sélectionner soigneusement le dépôt.
- Ne pas exécuter de consignes non fiables ; examiner les plans avant toute action.
- Aucune exécution automatique à partir de l'interface web : cette séparation est volontaire tant que l'authentification locale, l'isolation des processus et les autorisations ne sont pas implémentées.
- Aucun agent ne doit annoncer un test réussi sans preuve d'exécution.
- Les tests unitaires de cette tranche utilisent un faux processus Codex ; ils ne prouvent pas qu'une installation réelle de Codex fonctionne.
