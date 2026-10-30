# Recette V0.3.1 — Evidence & Security Gate

Date : 30 octobre 2026 (Europe/Paris).

État : **EN ATTENTE DE VALIDATION HUMAINE**. Cette recette rapporte les contrôles
du développeur ; elle ne constitue pas une vérification indépendante.

## Périmètre et préparation

- Branche vérifiée : `feature/v031-evidence-security`.
- Commit de départ : `df838051f88f4aab61ad4348396c79d20520793a`.
- Aucun changement suivi avant intervention. Aucun `AGENTS.md` trouvé dans le
  périmètre du projet inspecté ni dans ses parents ; le dépôt imbriqué non suivi
  `Orchestra-dev/` reste hors périmètre.
- Écriture vérifiée par fichiers temporaires supprimés après contrôle dans
  `orchestra`, `tests` et `docs`, et ouverture sans modification en lecture/écriture
  des deux fichiers Python concernés.
- Fichiers livrés : `orchestra/core.py`, `tests/test_core.py`, ce document.
- Aucun ajout de dépendance, aucune modification des permissions Windows.
- `.git` reste en lecture seule dans cette session, avec refus d'écriture dans
  les ACL. Aucun staging ni commit tenté, conformément à l'autorisation de reprise.
- Aucune fusion, publication, exécution d'agent réel ou migration de base utilisateur.

Contrôle final : `git diff --check` sans erreur, branche et HEAD inchangés.
Seuls les trois fichiers annoncés apparaissent comme nouveaux changements.
Les empreintes avant/après des éléments non suivis préexistants sont identiques :

| Élément | Nombre de fichiers | Empreinte SHA-256 du contrôle |
| --- | --- | --- |
| `mission.txt` | 1 | `677e63c95b59482357074f7dd1a706c50f886f678ec567fde7ed63373803ffd8` |
| `Orchestra-dev/` | 125 | `8451cf38ba236c605b3f05ef431cbf86bac8347a4ad5898c663cbdfe78000957` |

Le contrôle agrège les chemins relatifs encodés en UTF-8 et les octets des fichiers,
dans l'ordre des chemins triés. Ce sont des empreintes de préservation, pas les
empreintes standard d'une archive ou du seul contenu de `mission.txt`.

## Corrections

L'entrée dans `ATTENTE_VALIDATION_HUMAINE` exige au moins un critère. Tous doivent
être `CONFORME`, avec une preuve textuelle non vide et une date de vérification.
Les conditions sont revérifiées lors de chaque passage à `VALIDÉE`, y compris
depuis `PUBLICATION_ÉCHOUÉE`, ainsi qu'au passage à `PUBLIÉE`.

La méthode Python suivante enregistre un résultat déclaré et produit sa date UTC
au format ISO 8601. Elle accepte `CONFORME` ou `NON_CONFORME` et exige une preuve
non vide pour les deux résultats :

```python
registry.record_verification(
    criterion_id,
    status="CONFORME",
    evidence="Référence du rapport et résultat réellement constaté",
    actor="verifier",
)
```

Cet exemple illustre l'appel ; il n'atteste aucun test. Un critère nouvellement
créé reste `NON_VÉRIFIÉ`, avec `evidence` et `verified_at` à `NULL`.
`snapshot()` expose les nouveaux champs.

Un ajout de critère ou un nouvel enregistrement de vérification pendant l'attente
d'approbation renvoie la mission à `EN_VÉRIFICATION`. Cela s'applique même si le
nouveau résultat est encore `CONFORME`. Une nouvelle demande d'approbation est
nécessaire. L'invalidation est journalisée dans la même transaction.

Après approbation, l'ajout et la vérification sont refusés en `VALIDÉE`,
`PUBLICATION_ÉCHOUÉE` et `PUBLIÉE`. Aucune API d'édition ou de suppression des
critères n'est ajoutée. Les ajouts et résultats sont journalisés ; les résultats
enregistrés par cette méthode restent dans les événements après remplacement de
la preuve courante. Un événement peut conserver le même état avant et après.

Les opérations sensibles prennent un verrou SQLite `BEGIN IMMEDIATE` avant leurs
lectures. Modification, invalidation et événement sont atomiques ; l'échec du
journal provoque leur annulation complète. Les appels sont des transactions
autonomes : ne pas les imbriquer dans une transaction SQL manuelle sur `registry.db`.

## Migration et préservation

À l'ouverture d'une base, le registre inspecte les colonnes et ajoute seulement
les colonnes manquantes `evidence TEXT` et `verified_at TEXT`, dans une transaction.
Il ne supprime ni ne remplace aucune table ou ligne. Les identifiants, descriptions,
statuts, projets, missions, événements et index existants sont conservés.
Une réouverture ne réinitialise pas les preuves. Une base possédant déjà la colonne
`evidence` conserve son contenu lorsque `verified_at` est ajouté.

Les anciens critères `CONFORME` sans preuve/date restent lisibles mais ne passent
plus les contrôles de validation. Aucun résultat ni horodatage historique n'est
fabriqué. Une mission historique en attente doit recevoir une nouvelle vérification,
puis une nouvelle demande d'approbation.

Les anciens états déjà approuvés sont conservés. Si leurs preuves sont absentes,
leur publication ou retour à `VALIDÉE` est refusé et leurs critères restent gelés.
Cette version ne fournit pas de procédure de réouverture d'une mission approuvée :
un traitement explicite devra être décidé humainement, sans retouche SQL silencieuse.

Seules des bases temporaires créées par les tests ont été ouvertes/migrées pendant
la recette. La base réelle de l'utilisateur n'a pas été inspectée ni migrée.

## Exécutions réelles

Environnement : Windows, PowerShell, Python **3.14.2**. Commande exécutée :

```powershell
python -m unittest discover -s tests -v
```

| Exécution | Résultat réel | Durée unittest |
| --- | --- | --- |
| Avant modification | 11 tests, `OK`, code de sortie 0 | 0.314 s |
| Après les premières corrections et tests | 28 tests, `OK`, code de sortie 0 | 1.805 s |
| Après ajout du test de verrou pendant l'approbation | 29 tests, `OK`, code de sortie 0 | 1.925 s |

Résumé exact de la dernière exécution :

```text
Ran 29 tests in 1.925s

OK
```

Aucun échec observé lors de ces trois exécutions. La dernière suite comprend
22 tests du registre, 2 de migration et les 5 tests existants de l'adaptateur agent.
Le test existant de refus d'approbation par un agent a reçu un critère conforme
avec preuve afin d'atteindre réellement le contrôle de l'acteur.

| Exigence | Test(s) exécuté(s), noms abrégés sans préfixe `test_` |
| --- | --- |
| Aucun critère | `no_criteria_refused_without_state_or_event_change` |
| Critère non vérifié | `no_unverified_approval` |
| Preuve absente ou blanche | `verification_requires_evidence`, `missing_evidence_or_date_blocks_both_gates` |
| Conformité avec preuve | `conforming_evidence_allows_human_approval_and_publication` |
| Tous les critères conformes | `all_criteria_must_conform` |
| Validation prématurée | `premature_validation_refused_even_with_evidence`, `no_skipping_states` |
| Revérification à l'approbation | `final_approval_rechecks_status_and_existence`, `publication_retry_rechecks_evidence_and_actor` |
| Invalidation après ajout ou nouvelle vérification | `addition_invalidates_pending_approval_and_requires_new_review`, `reverification_invalidates_pending_approval_and_retains_history` |
| Gel après approbation | `criteria_frozen_after_approval_including_publication_retry` |
| Conservation SQLite | `legacy_data_preserved_and_migration_repeatable`, `partial_migration_preserves_existing_evidence` |
| Refus d'approbation par un agent | `no_agent_approval` |
| Persistance des preuves et date UTC | `evidence_and_utc_date_persist_on_reopen` |
| Annulation transactionnelle | `failed_event_write_rolls_back_criterion_and_invalidation` |
| Deux connexions SQLite | `other_connection_sees_invalidated_request`, `write_lock_covers_final_gate_and_approval` |

La migration complète vérifie aussi `PRAGMA integrity_check`, `foreign_key_check`,
la conservation d'un index et la continuation des identifiants d'événements.
Les manipulations SQL directes des tests concernent uniquement des bases temporaires
et simulent des données anciennes ou altérées. Aucune donnée préexistante du projet
n'est supprimée. Le test de verrou utilise deux connexions avec tentative d'écriture
pendant le contrôle final ; ce n'est pas un test de charge multiprocessus.

## Limites de sécurité et contrôles restants

**`actor="human"` n'est pas une authentification.** Un appelant peut fournir cette
chaîne ou bénéficier de sa valeur par défaut. Le serveur HTTP existant appelle
également les transitions avec cette valeur par défaut. Le refus d'un acteur
déclaré `agent` constitue uniquement un garde-fou logique ; il ne prouve pas que
l'approbation vient d'un humain. Aucun mécanisme d'identité ou de séparation fiable
des rôles n'a été ajouté.

La preuve reste un texte déclaré : ni sa véracité, ni l'existence de la pièce
référencée, ni son intégrité ne sont vérifiées automatiquement. La date correspond
à l'enregistrement par le registre, pas à une attestation d'exécution du test.
Un acteur ayant accès en écriture au fichier SQLite ou à `registry.db` peut modifier
les critères, les états et le journal en contournant les méthodes du registre.
Le journal n'est ni signé ni protégé contre l'altération.

La nouvelle méthode est disponible dans l'API Python seulement. Aucun formulaire
de vérification ni endpoint HTTP dédié n'a été ajouté. Les documents V0.1/V0.2
restent historiques ; la présente recette décrit le comportement V0.3.1.

Aucun test navigateur, test d'agent réel, contrôle CI distant ou recette humaine
n'a été exécuté pour cette mission. Le développeur a écrit et exécuté les tests :
aucune contre-expertise indépendante n'est revendiquée. Aucun défaut bloquant
n'a été révélé par la suite exécutée ; la restriction Git bloque toujours le commit.

La revue indépendante, la décision humaine et tout éventuel commit dans une
session autorisant l'écriture Git restent à effectuer. Aucune fusion ni publication
n'est autorisée par cette recette.
