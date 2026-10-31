# V0.3.2 — Rapport de sécurité et conception d'approbation

30 octobre 2026 — **EN ATTENTE DE VÉRIFICATION INDÉPENDANTE**.

## Décision appliquée

Le repli expressément autorisé par la mission est appliqué : **aucune nouvelle
approbation ni publication n'est possible**. L'architecture actuelle ne fournit
ni identité authentifiée, ni séparation entre l'utilisateur et les processus
agents disposant des mêmes accès locaux. Ajouter un mot de passe au même serveur
ou un jeton lisible par ces processus ne résoudrait pas ce problème.

`Registry.transition()` refuse systématiquement les destinations `VALIDÉE` et
`PUBLIÉE`, y compris un retour depuis `PUBLICATION_ÉCHOUÉE`. Il n'existe aucun
paramètre, cookie, variable d'environnement ou mode de développement pour lever
ce refus. `actor="human"` n'a plus aucun effet d'autorisation. Il peut subsister
comme ancien libellé déclaratif dans le journal ; il ne devient jamais une identité.

Cette version livre la vérification, les preuves et la demande d'examen. Elle ne
livre pas une authentification humaine opérationnelle. Le bouton d'approbation
indique explicitement son indisponibilité ; le blocage est aussi imposé au serveur
et au registre, indépendamment du bouton.

## Garanties effectivement implémentées

| Sujet | Comportement actuel |
| --- | --- |
| Identité fournie par le client | Champs non prévus, dont `actor`, `user`, `authenticated`, rejetés ; cookies et en-têtes d'identité n'accordent aucun droit |
| Transition sensible | Refus `AuthenticationRequired`, traduit en HTTP `401` pour une requête valide vers une mission existante |
| Sessions | Aucune session d'authentification créée, aucun `Set-Cookie`, aucun endpoint de connexion ; une prétendue session expirée ou valide n'accorde rien |
| Secrets | Aucun compte, mot de passe, clé privée ou secret d'authentification généré, stocké ou transmis à un agent |
| CSRF navigateur | Host exact, Origin exact obligatoire sur POST, en-tête `X-Orchestra-Request: 1`, JSON uniquement, refus des origines croisées et de la prérequête CORS |
| Concurrence | `BEGIN IMMEDIATE`, version monotone des critères, comparaison de `expected_revision` dans la transaction ; une écriture obsolète retourne `409` |
| Invalidation | Ajout ou nouvelle vérification incrémente la version et renvoie une demande en attente à `EN_VÉRIFICATION` |
| Preuves | Texte explicite et date UTC ; nouveau journal structuré, indépendant des motifs libres des transitions |
| Journal des refus | Mission, version courante, cible, motif fixe du refus, date, identité authentifiée absente ; refus validement adressés au registre persistants |
| Tentatives répétées | Au plus 10 tentatives sensibles et 120 POST par minute pour le processus serveur, compteurs protégés par verrou ; réponse `429` avec `Retry-After: 60` |
| Erreurs | Réponses JSON et codes distincts ; pas d'exception interne ou de contenu de secret dans les journaux HTTP |

Les transitions préparatoires, notamment `PLAN_VALIDÉ`, restent des déclarations
de workflow non authentifiées. Elles n'accordent pas d'approbation humaine finale.
La création et la vérification restent accessibles aux clients locaux capables
d'appeler l'API. Les contraintes d'origine protègent contre des requêtes de sites
tiers dans le navigateur ; un programme local peut fabriquer ces en-têtes. Elles
ne constituent donc pas une authentification.

Les requêtes rejetées avant identification d'une mission (format, origine, limite
de débit) n'ajoutent pas de décision à son journal. Si le journal SQLite est
indisponible, la requête échoue sans transition. Les compteurs de débit sont
globaux au serveur, volatils et réinitialisés au redémarrage ; ils ne remplacent
pas une protection complète contre le déni de service.

## Limites qui empêchent une garantie d'identité

Le fichier SQLite, `registry.db`, le code et la configuration restent accessibles
aux processus qui possèdent les droits Windows correspondants. Un tel processus
peut contourner les méthodes, altérer le journal ou modifier le programme. Le
blocage est une garantie du chemin applicatif livré, pas une protection contre
un attaquant contrôlant le même compte Windows ou le fichier de base.

Une preuve textuelle ne prouve ni l'exécution réelle d'un test ni l'intégrité du
fichier cité. Les anciennes décisions et vérifications ne sont pas authentifiées
rétroactivement. Les événements V0.3.1 reconnus sont importés une fois comme
`legacy-untrusted`, sans réécrire leur texte d'origine. Un nouveau motif libre
ne peut pas apparaître comme résultat structuré de vérification.

L'accès en lecture au tableau de bord n'est pas authentifié. Ne pas y placer de
secrets. Le serveur standard Python, les lectures de journal sans pagination et
les compteurs en mémoire ne sont pas dimensionnés pour un service exposé. Les
corps HTTP sont limités à 65 536 octets, avec délai de socket de 10 secondes ;
la vidange d'un corps refusé est bornée à 65 537 octets. Une fermeture par un client
malveillant ou un corps excessivement grand peut toujours interrompre le transport.

## Conception proposée — non implémentée

La séparation des droits doit précéder l'activation de l'approbation. Cette
proposition reste à spécifier et à vérifier indépendamment ; elle n'est pas une
garantie du code actuel.

1. **Service de confiance séparé.** Un service sous une identité Windows distincte
   possède seul les données d'approbation, le registre faisant autorité et les clés.
   Les agents passent par une API limitée ; ils n'ont accès ni aux fichiers, ni à
   la mémoire, ni au débogage, ni à la configuration du service. Son code et sa
   chaîne de mise à jour ne sont pas modifiables par les agents. La préparation de
   ces droits sera une opération administrative distincte ; aucune ACL n'est
   modifiée dans cette mission.
2. **Enrôlement humain de confiance.** L'identité et son rôle d'approbateur sont
   établis hors de l'API agent, selon une procédure administrée. Utiliser une
   authentification éprouvée avec vérification de l'utilisateur, par exemple un
   authentificateur WebAuthn validé par une bibliothèque auditée. L'interface
   d'approbation appartient au service de confiance et présente la mission, les
   critères et les preuves réellement autorisés par le serveur. Une clé publique
   librement enregistrée par un client ne suffit pas.
3. **Session courte.** Proposition à valider : durée absolue de cinq minutes,
   inactivité maximale d'une minute, contrôle des délais côté serveur, rotation à
   la connexion et révocation à la fermeture. Cookies opaques `__Host-...`,
   `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, sans attribut Domain, uniquement
   sur une origine HTTPS de confiance. Conserver seulement l'empreinte du jeton
   côté serveur ; aucun jeton dans URL, localStorage, consigne ou journal. Un
   transport local seul n'est pas une preuve d'identité.
4. **Consentement par décision.** Le serveur émet un défi à usage unique lié à
   l'identifiant de mission, la version monotone et l'empreinte canonique des
   critères/preuves, l'action exacte, l'identité et une expiration courte (proposition :
   90 secondes). L'utilisateur confirme ce contenu, avec vérification de présence
   et d'identité. Authentifier une session ne suffit pas à approuver automatiquement
   toutes les missions.
5. **Consommation atomique.** Sous verrou transactionnel : vérifier l'identité, le
   rôle, le défi, son expiration, sa non-consommation, la version et tous les critères.
   Consommer le défi, enregistrer la décision et changer l'état dans la même
   transaction. Toute modification invalide les défis en attente. Un rejeu, une
   autre mission ou deux consommations concurrentes doivent être refusés.
6. **CSRF et tentatives répétées.** Ajouter un jeton CSRF lié à la session, contrôler
   Origin et Fetch Metadata, maintenir les mutations hors de GET et une politique
   CORS fermée. Limiter les essais par identité et origine, avec temporisation,
   erreurs uniformes et surveillance. Éviter un verrouillage permanent exploitable
   pour bloquer l'utilisateur. Ne jamais journaliser les identifiants secrets.
7. **Processus agents.** Construire un environnement minimal explicite pour les
   sous-processus ; aucun secret d'approbation hérité via variables, fichiers,
   descripteurs, presse-papiers ou profil navigateur partagé. Le lanceur actuel
   n'assure pas cette isolation : aucun secret d'approbation ne doit lui être confié.
8. **Journal et récupération.** Enregistrer identité vérifiée, mission, version,
   empreinte, action, résultat et date dans le service protégé ; sauvegarde et audit
   séparés. Prévoir révocation des appareils, récupération de compte et arrêt sûr
   si le service d'authentification ou le journal est indisponible.

Le lien entre transaction examinée, autorisation serveur et usage unique suit les
principes d'[OWASP Transaction Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).
Les attributs de cookies et expirations proposés s'appuient sur
[OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
Les contrôles d'origine et d'en-têtes suivent
[OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
Le choix du service séparé et les durées ci-dessus sont des propositions pour ce
projet, pas une certification apportée par ces références.

## Conditions avant activation

Une autre mission devra prouver l'isolation réelle des agents, l'enrôlement,
l'authentification positive, l'expiration effective, la révocation, le rejet
intermission, l'invalidation des versions, la consommation unique concurrente et
la protection du journal. La revue doit être indépendante de l'auteur du code et
des tests. Tant que ces preuves manquent, conserver le refus systématique actuel.
