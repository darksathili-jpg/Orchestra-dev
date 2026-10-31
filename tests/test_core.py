import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from orchestra.core import AuthenticationRequired, Registry, RevisionConflict

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "db.sqlite"
        self.r = Registry(self.path)
        self.project = self.r.add_project("Microduck")
        self.mission = self.r.add_mission(self.project, "Test movements")

    def tearDown(self):
        self.r.close()
        self.tmp.cleanup()

    def test_persistence(self):
        self.r.close()
        self.r = Registry(self.path)
        self.assertEqual(self.r.snapshot()["missions"][0]["title"], "Test movements")

    def test_no_skipping_states(self):
        with self.assertRaises(ValueError):
            self.r.transition(self.mission, "EN_EXÉCUTION", "skip")

    def test_no_unverified_approval(self):
        self.r.add_criterion(self.mission, "Animation verified")
        criterion = self.r.snapshot()["criteria"][0]
        self.assertEqual(criterion["status"], "NON_VÉRIFIÉ")
        self.assertIsNone(criterion["evidence"])
        self.assertIsNone(criterion["verified_at"])
        for state in ("SPÉCIFIÉE", "PLAN_VALIDÉ", "EN_EXÉCUTION", "EN_VÉRIFICATION"):
            self.r.transition(self.mission, state, "progress")
        with self.assertRaises(ValueError):
            self.r.transition(self.mission, "ATTENTE_VALIDATION_HUMAINE", "not tested")

    def test_mission_brief(self):
        self.r.add_criterion(self.mission, "One movement per instruction")
        brief = self.r.mission_brief(self.mission)
        self.assertIn("Microduck", brief)
        self.assertIn("One movement per instruction", brief)
        self.assertIn("sans modifier les fichiers", brief)

    def test_unknown_mission_brief(self):
        with self.assertRaises(KeyError):
            self.r.mission_brief("missing")

    def test_no_agent_approval(self):
        criterion = self.r.add_criterion(self.mission, "Animation verified")
        self.r.record_verification(criterion, "CONFORME", "Local test report")
        for state in ("SPÉCIFIÉE", "PLAN_VALIDÉ", "EN_EXÉCUTION", "EN_VÉRIFICATION", "ATTENTE_VALIDATION_HUMAINE"):
            self.r.transition(self.mission, state, "progress")
        with self.assertRaises(PermissionError):
            self.r.transition(self.mission, "VALIDÉE", "agent claim", actor="agent")

    def advance_to_verification(self):
        for state in ("SPÉCIFIÉE", "PLAN_VALIDÉ", "EN_EXÉCUTION", "EN_VÉRIFICATION"):
            self.r.transition(self.mission, state, "progress")

    def ready_for_approval(self):
        criterion = self.r.add_criterion(self.mission, "Animation verified")
        self.r.record_verification(criterion, "CONFORME", "Report: 12 checks passed")
        self.advance_to_verification()
        self.r.transition(self.mission, "ATTENTE_VALIDATION_HUMAINE", "ready")
        return criterion

    def test_no_criteria_refused_without_state_or_event_change(self):
        self.advance_to_verification()
        before = self.r.snapshot()
        with self.assertRaisesRegex(ValueError, "At least one"):
            self.r.transition(self.mission, "ATTENTE_VALIDATION_HUMAINE", "empty")
        self.assertEqual(self.r.snapshot(), before)

    def test_verification_requires_evidence(self):
        criterion = self.r.add_criterion(self.mission, "Check")
        before = self.r.snapshot()
        for evidence in (None, "", " \t\n", 123):
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                self.r.record_verification(criterion, "CONFORME", evidence)
            self.assertEqual(self.r.snapshot(), before)

    def test_verification_rejects_invalid_status_and_unknown_criterion(self):
        criterion = self.r.add_criterion(self.mission, "Check")
        before = self.r.snapshot()
        for status in ("NON_VÉRIFIÉ", "PASS", None):
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.r.record_verification(criterion, status, "report")
        with self.assertRaises(KeyError):
            self.r.record_verification("missing", "CONFORME", "report")
        self.assertEqual(self.r.snapshot(), before)

    def test_conforming_evidence_allows_request_but_no_declared_human_approval(self):
        self.ready_for_approval()
        for target in ("VALIDÉE", "PUBLIÉE"):
            for actor in ("human", "agent", "admin", None):
                with self.subTest(target=target, actor=actor), self.assertRaises(AuthenticationRequired):
                    self.r.transition(self.mission, target, "Claimed approval", actor=actor)
        self.assertEqual(self.r.snapshot()["missions"][0]["state"], "ATTENTE_VALIDATION_HUMAINE")
        decisions = self.r.mission_review(self.mission)["decisions"]
        self.assertEqual(len(decisions), 8)
        self.assertTrue(all(d["authenticated_subject"] is None for d in decisions))

    def test_all_criteria_must_conform(self):
        good = self.r.add_criterion(self.mission, "First")
        bad = self.r.add_criterion(self.mission, "Second")
        self.r.record_verification(good, "CONFORME", "First passed")
        self.r.record_verification(bad, "NON_CONFORME", "Second failed")
        self.advance_to_verification()
        with self.assertRaises(ValueError):
            self.r.transition(self.mission, "ATTENTE_VALIDATION_HUMAINE", "one failed")

    def test_premature_validation_refused_even_with_evidence(self):
        criterion = self.r.add_criterion(self.mission, "Check")
        self.r.record_verification(criterion, "CONFORME", "report")
        self.advance_to_verification()
        before = self.r.snapshot()
        with self.assertRaises(AuthenticationRequired):
            self.r.transition(self.mission, "VALIDÉE", "skip review")
        self.assertEqual(self.r.snapshot(), before)

    def test_missing_evidence_or_date_blocks_both_gates(self):
        criterion = self.ready_for_approval()
        for current, target in (("EN_VÉRIFICATION", "ATTENTE_VALIDATION_HUMAINE"),
                                ("ATTENTE_VALIDATION_HUMAINE", "VALIDÉE")):
            for field in ("evidence", "verified_at"):
                for value in (None, "", " \t\n"):
                    with self.subTest(target=target, field=field, value=value):
                        with self.r.db:
                            self.r.db.execute("UPDATE missions SET state=? WHERE id=?", (current, self.mission))
                            self.r.db.execute("UPDATE criteria SET evidence=?,verified_at=? WHERE id=?",
                                              ("report", "2026-10-30T12:00:00+00:00", criterion))
                            self.r.db.execute(f"UPDATE criteria SET {field}=? WHERE id=?", (value, criterion))
                        before = self.r.snapshot()
                        with self.assertRaises(AuthenticationRequired if target == "VALIDÉE" else ValueError):
                            self.r.transition(self.mission, target, "incomplete evidence")
                        self.assertEqual(self.r.snapshot(), before)

    def test_final_approval_fails_closed_even_with_corrupted_criteria(self):
        criterion = self.ready_for_approval()
        for status in ("NON_VÉRIFIÉ", "NON_CONFORME"):
            with self.subTest(status=status):
                with self.r.db:
                    self.r.db.execute("UPDATE criteria SET status=? WHERE id=?", (status, criterion))
                with self.assertRaises(AuthenticationRequired):
                    self.r.transition(self.mission, "VALIDÉE", "stale approval")
        with self.r.db:
            self.r.db.execute("DELETE FROM criteria WHERE id=?", (criterion,))
        with self.assertRaises(AuthenticationRequired):
            self.r.transition(self.mission, "VALIDÉE", "criteria removed")

    def test_addition_invalidates_pending_approval_and_requires_new_review(self):
        self.ready_for_approval()
        criterion = self.r.add_criterion(self.mission, "Additional check")
        snapshot = self.r.snapshot()
        self.assertEqual(snapshot["missions"][0]["state"], "EN_VÉRIFICATION")
        self.assertEqual(snapshot["events"][-1]["previous_state"], "ATTENTE_VALIDATION_HUMAINE")
        self.assertIn("invalidated", snapshot["events"][-1]["reason"])
        with self.assertRaises(AuthenticationRequired):
            self.r.transition(self.mission, "VALIDÉE", "old request")
        with self.assertRaises(ValueError):
            self.r.transition(self.mission, "ATTENTE_VALIDATION_HUMAINE", "not yet checked")
        self.r.record_verification(criterion, "CONFORME", "Additional check passed")
        self.r.transition(self.mission, "ATTENTE_VALIDATION_HUMAINE", "new request")
        with self.assertRaises(AuthenticationRequired):
            self.r.transition(self.mission, "VALIDÉE", "new approval")

    def test_reverification_invalidates_pending_approval_and_retains_history(self):
        criterion = self.ready_for_approval()
        self.r.record_verification(criterion, "CONFORME", "Updated report", actor="verifier")
        snapshot = self.r.snapshot()
        self.assertEqual(snapshot["missions"][0]["state"], "EN_VÉRIFICATION")
        self.assertEqual(snapshot["criteria"][0]["evidence"], "Updated report")
        self.assertTrue(any("Report: 12 checks passed" in event["reason"] for event in snapshot["events"]))
        self.assertEqual(snapshot["events"][-1]["actor"], "verifier")
        with self.assertRaises(AuthenticationRequired):
            self.r.transition(self.mission, "VALIDÉE", "old request")

    def test_criteria_frozen_after_approval_including_publication_retry(self):
        criterion = self.ready_for_approval()
        # Historical approved states are fixture data, never a successful new approval.
        for target in ("VALIDÉE", "PUBLICATION_ÉCHOUÉE", "PUBLIÉE"):
            with self.r.db:
                self.r.db.execute("UPDATE missions SET state=? WHERE id=?", (target, self.mission))
            with self.subTest(state=target):
                before = self.r.snapshot()
                with self.assertRaisesRegex(ValueError, "frozen"):
                    self.r.add_criterion(self.mission, "Silent addition")
                with self.assertRaisesRegex(ValueError, "frozen"):
                    self.r.record_verification(criterion, "NON_CONFORME", "Changed result")
                self.assertEqual(self.r.snapshot(), before)

    def test_historical_publication_retry_requires_real_authentication(self):
        criterion = self.ready_for_approval()
        with self.r.db:
            self.r.db.execute("UPDATE missions SET state='VALIDÉE' WHERE id=?", (self.mission,))
        with self.assertRaises(PermissionError):
            self.r.transition(self.mission, "PUBLIÉE", "agent", actor="agent")
        self.r.transition(self.mission, "PUBLICATION_ÉCHOUÉE", "failed")
        with self.assertRaises(PermissionError):
            self.r.transition(self.mission, "VALIDÉE", "agent retry", actor="agent")
        with self.r.db:
            self.r.db.execute("UPDATE criteria SET evidence=NULL WHERE id=?", (criterion,))
        with self.assertRaises(AuthenticationRequired):
            self.r.transition(self.mission, "VALIDÉE", "retry without evidence")

    def test_evidence_and_utc_date_persist_on_reopen(self):
        criterion = self.r.add_criterion(self.mission, "Check")
        before = datetime.now(timezone.utc)
        self.r.record_verification(criterion, "CONFORME", "  Résultat: 12/12 — rapport local  ")
        snapshot = self.r.snapshot()
        verification = snapshot["criteria"][0]
        self.assertEqual(verification["evidence"], "Résultat: 12/12 — rapport local")
        stamp = datetime.fromisoformat(verification["verified_at"])
        self.assertEqual(stamp.tzinfo, timezone.utc)
        self.assertLessEqual(before, stamp)
        self.assertLessEqual(stamp, datetime.now(timezone.utc))
        self.r.close()
        self.r = Registry(self.path)
        self.assertEqual(self.r.snapshot(), snapshot)

    def test_failed_event_write_rolls_back_criterion_and_invalidation(self):
        criterion = self.ready_for_approval()
        self.r.db.execute("""CREATE TRIGGER reject_event BEFORE INSERT ON events
                             BEGIN SELECT RAISE(ABORT, 'event unavailable'); END""")
        before = self.r.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):
            self.r.record_verification(criterion, "NON_CONFORME", "failure")
        self.assertEqual(self.r.snapshot(), before)
        with self.assertRaises(sqlite3.IntegrityError):
            self.r.add_criterion(self.mission, "new check")
        self.assertEqual(self.r.snapshot(), before)
        with self.assertRaises(sqlite3.IntegrityError):
            self.r.transition(self.mission, "BLOQUÉE", "blocked")
        self.assertEqual(self.r.snapshot(), before)

    def test_other_connection_sees_invalidated_request(self):
        self.ready_for_approval()
        with Registry(self.path) as other:
            other.add_criterion(self.mission, "Other connection's check")
            with self.assertRaises(AuthenticationRequired):
                self.r.transition(self.mission, "VALIDÉE", "stale request")
            self.assertEqual(self.r.snapshot(), other.snapshot())

    def test_write_lock_covers_evidence_gate_and_approval_request(self):
        criterion = self.ready_for_approval()
        self.r.record_verification(criterion, "CONFORME", "Updated report")
        attempts = []
        with Registry(self.path) as other:
            other.db.execute("PRAGMA busy_timeout=0")

            def try_concurrent_change(statement):
                if statement.startswith("SELECT status,evidence,verified_at"):
                    try:
                        other.record_verification(criterion, "NON_CONFORME", "Concurrent failure")
                    except sqlite3.OperationalError as exc:
                        attempts.append(str(exc))
                    else:
                        attempts.append("unexpected write success")

            self.r.db.set_trace_callback(try_concurrent_change)
            try:
                self.r.transition(self.mission, "ATTENTE_VALIDATION_HUMAINE", "request review")
            finally:
                self.r.db.set_trace_callback(None)
            self.assertEqual(attempts, ["database is locked"])
            self.assertEqual(other.snapshot()["criteria"][0]["status"], "CONFORME")
            self.assertEqual(other.snapshot()["missions"][0]["state"], "ATTENTE_VALIDATION_HUMAINE")
            other.record_verification(criterion, "NON_CONFORME", "Later result")
            self.assertEqual(self.r.snapshot()["missions"][0]["state"], "EN_VÉRIFICATION")


class MigrationTests(unittest.TestCase):
    def test_v031_evidence_and_history_migrate_without_inventing_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v031.sqlite"
            db = sqlite3.connect(path)
            try:
                db.executescript("""
                    CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, repo TEXT, created_at TEXT NOT NULL);
                    CREATE TABLE missions(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                        title TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
                    CREATE TABLE criteria(id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(id),
                        description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'NON_VÉRIFIÉ'
                        CHECK(status IN ('NON_VÉRIFIÉ','CONFORME','NON_CONFORME')), evidence TEXT, verified_at TEXT);
                    CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL REFERENCES missions(id),
                        previous_state TEXT, next_state TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT NOT NULL, timestamp TEXT NOT NULL);
                    INSERT INTO projects VALUES ('p','Projet',NULL,'2026-10-29');
                    INSERT INTO missions VALUES ('m','p','Mission','ATTENTE_VALIDATION_HUMAINE','2026-10-29');
                    INSERT INTO criteria VALUES ('c','m','Contrôle','CONFORME','Rapport conservé','2026-10-29T12:00:00+00:00');
                    INSERT INTO events VALUES (1,'m','EN_VÉRIFICATION','EN_VÉRIFICATION',
                        'Criterion verification: {"criterion_id":"c","status":"CONFORME","evidence":"Rapport conservé","verified_at":"2026-10-29T12:00:00+00:00"}',
                        'human','2026-10-29T12:00:00+00:00');
                """)
            finally:
                db.close()
            with Registry(path) as registry:
                review = registry.mission_review('m')
                self.assertEqual(review["mission"]["criteria_revision"], 0)
                self.assertEqual(review["criteria"][0]["evidence"], "Rapport conservé")
                self.assertEqual(review["verification_history"][0]["evidence"], "Rapport conservé")
                self.assertEqual(review["verification_history"][0]["source"], "legacy-untrusted")
                self.assertEqual(review["decisions"], [])
                self.assertFalse(review["approval_available"])
                registry.record_verification('c', 'CONFORME', 'Rapport suivant', expected_revision=0)
                self.assertEqual(registry.mission_review('m')["mission"]["criteria_revision"], 1)
                with self.assertRaises(RevisionConflict):
                    registry.record_verification('c', 'CONFORME', 'Rejeu', expected_revision=0)
                expected = registry.mission_review('m')
            with Registry(path) as registry:
                self.assertEqual(registry.mission_review('m'), expected)
                self.assertEqual(registry.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(registry.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_legacy_data_preserved_and_migration_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite"
            db = sqlite3.connect(path)
            db.row_factory = sqlite3.Row
            try:
                db.executescript("""
                    CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, repo TEXT, created_at TEXT NOT NULL);
                    CREATE TABLE missions(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                        title TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
                    CREATE TABLE criteria(id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(id),
                        description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'NON_VÉRIFIÉ'
                        CHECK(status IN ('NON_VÉRIFIÉ','CONFORME','NON_CONFORME')));
                    CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL REFERENCES missions(id),
                        previous_state TEXT, next_state TEXT NOT NULL, reason TEXT NOT NULL, actor TEXT NOT NULL, timestamp TEXT NOT NULL);
                    INSERT INTO projects VALUES ('p','Projet préservé','C:\\projets\\demo','2025-01-01');
                    INSERT INTO missions VALUES ('m','p','Mission historique','ATTENTE_VALIDATION_HUMAINE','2025-01-02');
                    INSERT INTO criteria VALUES ('c','m','Critère historique','CONFORME');
                    INSERT INTO events VALUES (42,'m','EN_VÉRIFICATION','ATTENTE_VALIDATION_HUMAINE','Historique','human','2025-01-03');
                    CREATE INDEX legacy_criteria_mission ON criteria(mission_id);
                """)
                original = {table: [dict(row) for row in db.execute(f"SELECT * FROM {table}")]
                            for table in ("projects", "missions", "criteria", "events")}
            finally:
                db.close()
            with Registry(path) as registry:
                migrated = registry.snapshot()
                for table, rows in original.items():
                    self.assertEqual([{key: row[key] for key in rows[0]} for row in migrated[table]], rows)
                self.assertIsNone(migrated["criteria"][0]["evidence"])
                self.assertIsNone(migrated["criteria"][0]["verified_at"])
                self.assertTrue(registry.db.execute("SELECT name FROM sqlite_master WHERE name='legacy_criteria_mission'").fetchone())
                with self.assertRaises(AuthenticationRequired):
                    registry.transition('m', 'VALIDÉE', 'legacy result is insufficient')
                registry.record_verification('c', 'CONFORME', 'New executed verification')
                self.assertEqual(registry.snapshot()["events"][-1]["id"], 43)
                self.assertEqual(registry.snapshot()["missions"][0]["state"], "EN_VÉRIFICATION")
                registry.transition('m', 'ATTENTE_VALIDATION_HUMAINE', 'new request')
                with self.assertRaises(AuthenticationRequired):
                    registry.transition('m', 'VALIDÉE', 'reviewed')
                expected = registry.snapshot()
            with Registry(path) as reopened:
                self.assertEqual(reopened.snapshot(), expected)
                self.assertEqual(reopened.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(reopened.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_partial_migration_preserves_existing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "partial.sqlite"
            db = sqlite3.connect(path)
            try:
                db.executescript("""
                    CREATE TABLE criteria(id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
                        description TEXT NOT NULL, status TEXT NOT NULL, evidence TEXT);
                    INSERT INTO criteria VALUES ('c','m','Check','CONFORME','Existing evidence');
                """)
            finally:
                db.close()
            with Registry(path) as registry:
                criterion = registry.snapshot()["criteria"][0]
                self.assertEqual(criterion["evidence"], "Existing evidence")
                self.assertIsNone(criterion["verified_at"])

if __name__ == "__main__":
    unittest.main()
