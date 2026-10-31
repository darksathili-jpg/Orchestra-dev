# Recette V0.3.2 — Human Approval & Evidence UI

Date : 30 octobre 2026 (Europe/Paris).

**État : EN ATTENTE DE VÉRIFICATION INDÉPENDANTE.**

Le parcours de vérification est implémenté. L'approbation humaine réelle n'est
pas activée : le repli prévu par la mission bloque les transitions sensibles,
faute d'isolation et d'authentification fiables dans l'architecture actuelle.
Voir [le rapport de sécurité](SECURITE_V032.md). Le parcours navigateur reste
non validé, car Playwright n'a pas pu être installé ni lancé dans cette session.

## Préparation et préservation

La branche `feature/v032-human-approval` était déjà active au démarrage. Elle et
`feature/v031-evidence-security` pointaient toutes deux sur
`8c4751252a09f3553be4365c02d99e41929db8d4` ; `git merge-base` a confirmé ce même
ancêtre. Aucune création supplémentaire de branche n'était nécessaire. Le dépôt
ne présentait aucun changement suivi. Aucun `AGENTS.md` n'a été trouvé dans le
périmètre inspecté ; le dépôt non suivi imbriqué reste hors périmètre.

L'écriture des dossiers `orchestra`, `tests`, `docs` et `web` a été vérifiée avec
des sondes temporaires retirées. `.git` reste en lecture seule dans la session et
ses ACL affichent des refus d'écriture. Aucun staging, commit, changement d'ACL,
fusion, push ou déploiement n'a été tenté. La recette V0.3.1 reste intacte.

Les empreintes composites avant/après des éléments non suivis sont identiques :

| Élément | Fichiers | SHA-256 du contrôle |
| --- | --- | --- |
| `mission.txt` | 1 | `677e63c95b59482357074f7dd1a706c50f886f678ec567fde7ed63373803ffd8` |
| `Orchestra-dev/` | 125 | `8451cf38ba236c605b3f05ef431cbf86bac8347a4ad5898c663cbdfe78000957` |

Le calcul concatène les chemins relatifs UTF-8 triés et les octets des fichiers ;
ce n'est pas une empreinte standard du seul contenu de `mission.txt`.
Aucune base utilisateur n'a été ouverte ni migrée. Les tests utilisent des bases
temporaires et des serveurs locaux arrêtés après exécution.

## Modifications livrées

- `orchestra/core.py` : refus systématique de `VALIDÉE` et `PUBLIÉE`, journal des
  refus, version des critères, contrôle transactionnel de version, vue cohérente
  d'examen, historique structuré et migration additive.
- `orchestra/server.py` : endpoints d'examen et de vérification, validation stricte
  des champs, protections d'origine, limitation des requêtes, erreurs HTTP distinctes.
- `web/index.html`, `web/app.js`, `web/style.css` : choix de mission, saisie d'un
  résultat et de sa preuve, date, blocages, historique, transitions préparatoires,
  décisions/refus, approbation explicitement indisponible, thèmes clair et sombre.
- `tests/test_core.py`, `tests/test_server.py` : non-régression, migration, HTTP réel
  sur loopback, absence d'authentification, concurrence et rejeu.
- `tests/e2e/evidence.spec.cjs`, `tests/e2e/dashboard.spec.cjs`,
  `playwright.config.cjs` : parcours navigateur et thèmes ; chaque exécution prévue
  utilise un nouveau dossier temporaire pour base, captures, traces et rapport.
- Le présent document et `docs/SECURITE_V032.md`.

Le dépôt inspecté ne contenait qu'un thème sombre explicite. Il est conservé et
un thème clair est ajouté avec couleurs de champs et boutons explicites, choix
persistant et préférence système initiale. Leur lisibilité réelle reste à vérifier
dans le navigateur ; les contrôles Playwright de contraste sont écrits, non exécutés.

Les brouillons de preuve sont conservés après un refus de version obsolète ;
l'utilisateur peut relire puis actualiser la mission. Aucun contenu de preuve
n'est interprété comme HTML. Les libellés d'acteurs historiques ne sont pas
présentés comme des identités authentifiées.

## API et migration

| Route | Usage |
| --- | --- |
| `GET /api/review/{mission_id}` | Mission, version, critères, blocages, historique, refus, étapes possibles |
| `POST /api/verifications` | `criterion_id`, `status`, `evidence`, `expected_revision` |
| `POST /api/criteria` | `mission_id`, `description`, `expected_revision` |
| `POST /api/transition` | `mission_id`, `target`, `reason`, `expected_revision` |
| `GET /api/auth/status` | Signale explicitement l'absence d'authentification et d'approbation disponibles |

Les routes de création de projet/mission, snapshot et consigne restent disponibles.
Les POST exigent `Content-Type: application/json`, l'Origin exact du serveur et
`X-Orchestra-Request: 1`. Les champs supplémentaires sont refusés ; les tailles et
types sont contrôlés. Ces en-têtes ne constituent pas une preuve d'identité.

Codes vérifiés : `201` succès d'écriture ; `400` contenu invalide ; `401` absence
d'authentification pour une transition sensible ; `403` origine/en-tête refusé ;
`404` ressource inconnue ; `405` méthode refusée ; `409` version ou données en
conflit ; `413` corps trop grand ; `415` type de contenu incorrect ; `429` limite
de requêtes ; `500` erreur interne masquée ; `503` registre indisponible.

La migration conserve les colonnes et données historiques, ajoute
`missions.criteria_revision`, `events.verification_data`,
`events.verification_source` et la table `approval_decisions`. Les nouveaux champs
des événements historiques sont renseignés uniquement pour les anciens résultats
reconnus, sans réécrire leurs champs existants. Ils sont marqués `legacy-untrusted`.
Les résultats futurs sont structurés dans la transaction de vérification : un
motif de transition libre ne peut pas se faire passer pour une vérification.

Une réouverture ne réimporte pas les nouveaux textes libres. La version démarre
à zéro sur les anciennes missions puis augmente à chaque ajout/vérification.
Ce compteur ne constitue pas à lui seul une autorisation humaine. Les états déjà
approuvés sont préservés, les critères y restent gelés et la publication est bloquée.

## Tests réussis — exécutés réellement

Environnement : Windows / PowerShell, Python **3.14.2**, Node **22.13.1**.

```powershell
python -m unittest discover -s tests -v
```

Dernière exécution après les corrections Python finales, code de sortie **0** :

```text
Ran 44 tests in 3.736s

OK
```

Répartition : 22 tests de registre, 3 tests de migration, 5 tests existants
d'adaptateur agent, 13 tests de serveur HTTP et 1 test de limitation concurrente.
Les serveurs HTTP et les connexions SQLite sont réels ; l'identité humaine n'est
pas simulée pour autoriser une transition.

| Contrôle demandé | Couverture exécutée |
| --- | --- |
| Approbation non authentifiée | Refus `401`, état préservé et journal persistant |
| Identité simplement déclarée | Champs libres refusés ; `actor="human"`, en-têtes et cookies n'autorisent rien |
| Session expirée | Cookie **présenté** comme expiré refusé, comme tout cookie ; pas de vrai mécanisme de session à tester |
| Requête non autorisée | Origine absente/fausse, Host incorrect, en-tête manquant, requête intersite |
| Modification des critères | Invalidation de l'attente, incrément de version, refus `409` d'une version obsolète |
| Persistance des preuves | Réouverture SQLite, dates et historique conservés |
| Journal des décisions | Refus lié à mission/version, aucune identité inventée, échec du journal sans approbation |
| Bases existantes | Schéma ancien, migration partielle des preuves, schéma V0.3.1, intégrité et clés étrangères |
| Erreurs HTTP | Codes indiqués ci-dessus, JSON malformé, types/tailles invalides, clés dupliquées |
| Concurrence | Deux vérifications de même version : un `201` et un `409` ; quatre approbations concurrentes : quatre refus |
| Réutilisation | Écriture rejouée refusée ; cookie/autorisation prétendus réutilisés sans jamais accorder d'approbation |
| Tentatives répétées | Dix refus sensibles puis `429`, expiration de fenêtre testée avec horloge contrôlée |
| Historique falsifié | Motif libre imitant une vérification exclu de l'historique structuré, même après réouverture |

Les tests V0.3.1 qui autorisaient une validation via `actor="human"` ont été adaptés
au refus désormais obligatoire. Les états historiques approuvés sont créés
explicitement dans les seules bases de test pour contrôler leur gel ; ils ne sont
pas présentés comme une authentification réussie.

Autres contrôles exécutés sans erreur : `node --check` sur `web/app.js`, la
configuration Playwright et les deux fichiers E2E ; `git diff --check`.
Ces contrôles de syntaxe ne prouvent pas le rendu ni le parcours navigateur.

## Échecs observés et corrigés

La suite existante a d'abord passé ses **29 tests en 1.766 s**. Après adaptation du
registre, elle a passé **29 tests en 1.917 s**.

Deux exécutions intermédiaires avec les tests HTTP ont échoué :

- **42 tests, 1 erreur, 5.132 s** : réception de `413` interrompue par Windows
  (`ConnectionAbortedError`, `WinError 10053`) lors du refus d'un corps trop grand.
- **43 tests, 1 erreur, 5.323 s** : le même défaut de transport a été révélé sur
  le refus `405` d'une requête PUT contenant un corps.

Le serveur vidange désormais un volume borné de corps refusé avant de fermer la
connexion. La suite a ensuite passé **43 tests en 5.198 s**, puis **44 tests en
5.334 s** après ajout du contrôle d'historique, puis l'exécution finale ci-dessus.
Aucun échec Python ne subsiste dans cette dernière exécution.

## Playwright — blocage et contrôles non exécutés

`node_modules` était absent. Tentatives réellement effectuées :

1. Installation des dépendances déclarées, sans script ni fichier lock, en mode
   hors ligne : échec `ENOTCACHED` pour `@playwright/test`.
2. Installation normale, sans script ni lock, cache temporaire, zéro relance et
   délai réseau de dix secondes : échec **`EACCES`** sur
   `https://registry.npmjs.org/@playwright%2ftest`.
3. `npm.cmd run test:e2e -- --list` : code **1**, commande **`playwright` non reconnue**.

Aucune dépendance ajoutée à `package.json`, aucun contournement réseau ou changement
de permission. La collecte Playwright n'a pas démarré : **aucun scénario navigateur
exécuté, aucune capture produite**, aucun succès navigateur revendiqué.

Six scénarios sont écrits dans les sources (inventaire statique, non une collecte
réussie) : les deux existants ; le parcours de preuve jusqu'au blocage explicite
d'authentification ; le thème clair ; le thème sombre ; le conflit de brouillon
entre deux versions. Le parcours inclut une requête HTTP directe refusée, la
persistance, l'historique et l'invalidation après ajout. Il ne prétend pas tester
une approbation humaine positive, absente de cette version.

Après mise à disposition autorisée de Playwright et de Chromium, exécuter :

```powershell
npm.cmd run test:e2e -- --list
npm.cmd run test:e2e
```

La configuration annonce un dossier temporaire neuf `ORCHESTRA E2E artifacts` et
utilise une base distincte ; ne pas réutiliser un ancien dossier de preuve. Le
serveur du test exige le port 8766 libre et ne réutilise pas un serveur existant.

Restent non exécutés : rendu et contraste réels, parcours et captures navigateur,
authentification positive, expiration réelle d'une session émise par un fournisseur,
consommation d'une véritable autorisation humaine, isolation Windows d'un service
de confiance, tests d'agent réel, CI et vérification indépendante.

## Risques résiduels et réception

Le registre reste modifiable par un processus possédant l'accès direct au fichier
SQLite ; le journal n'est pas inviolable. La véracité des preuves déclarées n'est
pas garantie. Le repli bloque l'approbation applicative mais ne sécurise pas le
compte Windows contre ses propres processus. Les limites et la conception d'un
service séparé sont détaillées dans [SECURITE_V032.md](SECURITE_V032.md).

Le développeur a écrit et exécuté les tests : ceci n'est pas une contre-expertise.
L'absence de recette navigateur et d'authentification opérationnelle interdit de
présenter la mission comme un parcours d'approbation sécurisé complet et validé.
Les modifications restent non commitées, sans fusion ni publication.
