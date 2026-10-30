## Prototype de noyau V0.1

Prérequis : Python 3.11+.

Depuis la racine du dépôt :

```powershell
python -m unittest discover -s tests -v
```

Le module `orchestra.core.Registry` implémente une persistance SQLite minimale : projets, missions, critères et journal des transitions.

**Limites connues** : pas encore d'interface Electron/React, pas de serveur FastAPI, pas d'agents exécutables, pas d'authentification, pas de gestion de concurrence ni de déploiement. La colonne `actor` n'est pas une preuve d'identité : les protections actuelles sont seulement des garde-fous logiques, pas une frontière de sécurité. Les critères ne disposent pas encore d'API de vérification ; l'état initial est toujours `NON_VÉRIFIÉ`.

Les tests sont ajoutés mais doivent être exécutés dans un environnement Python réel et en CI avant toute affirmation de réussite.
