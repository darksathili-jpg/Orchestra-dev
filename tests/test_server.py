import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from orchestra.core import Registry
from orchestra.server import RequestLimit, Server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "registry.sqlite"
        with Registry(self.path) as registry:
            self.project = registry.add_project("Projet HTTP")
            self.mission = registry.add_mission(self.project, "Mission HTTP")
            self.criterion = registry.add_criterion(self.mission, "Critère HTTP")
        self.server = Server(("127.0.0.1", 0), self.path)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def request(self, method, path, data=None, headers=None, raw=None):
        request_headers = {"Origin": self.origin, "X-Orchestra-Request": "1", "Content-Type": "application/json"}
        for key, value in (headers or {}).items():
            if value is None:
                request_headers.pop(key, None)
            else:
                request_headers[key] = value
        body = raw if raw is not None else (json.dumps(data).encode("utf-8") if data is not None else None)
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=15)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            body = response.read()
            return response.status, json.loads(body), dict(response.getheaders())
        finally:
            connection.close()

    def review(self):
        status, data, _ = self.request("GET", "/api/review/" + self.mission)
        self.assertEqual(status, 200)
        return data

    def transition(self, target, headers=None, extra=None):
        return self.request("POST", "/api/transition", {
            "mission_id": self.mission, "target": target, "reason": "Test réellement exécuté",
            "expected_revision": self.review()["mission"]["criteria_revision"], **(extra or {})}, headers)

    def verify(self, status="CONFORME", evidence="Rapport HTTP : résultat constaté", revision=None):
        if revision is None:
            revision = self.review()["mission"]["criteria_revision"]
        return self.request("POST", "/api/verifications", {
            "criterion_id": self.criterion, "status": status, "evidence": evidence, "expected_revision": revision})

    def ready(self):
        self.assertEqual(self.verify()[0], 201)
        for state in ("SPÉCIFIÉE", "PLAN_VALIDÉ", "EN_EXÉCUTION", "EN_VÉRIFICATION", "ATTENTE_VALIDATION_HUMAINE"):
            self.assertEqual(self.transition(state)[0], 201)

    def test_unauthenticated_approval_refused_and_journal_persists(self):
        self.ready()
        revision = self.review()["mission"]["criteria_revision"]
        code, data, headers = self.transition("VALIDÉE")
        self.assertEqual(code, 401)
        self.assertEqual(data["code"], "AUTHENTICATION_UNAVAILABLE")
        self.assertNotIn("Set-Cookie", headers)
        with Registry(self.path) as reopened:
            review = reopened.mission_review(self.mission)
            self.assertEqual(review["mission"]["state"], "ATTENTE_VALIDATION_HUMAINE")
            decision = review["decisions"][0]
            self.assertEqual(decision["criteria_revision"], revision)
            self.assertEqual(decision["mission_id"], self.mission)
            self.assertEqual(decision["outcome"], "REFUSED")
            self.assertIsNone(decision["authenticated_subject"])
            self.assertTrue(decision["timestamp"])

    def test_declared_identity_or_authorization_cannot_authenticate(self):
        for claim in ({"actor": "human"}, {"user": "admin"}, {"authenticated": True}, {"authorization": "grant"}):
            with self.subTest(claim=claim):
                self.assertEqual(self.transition("VALIDÉE", extra=claim)[0], 400)
        self.assertEqual(self.transition("VALIDÉE", headers={"X-User": "human", "Authorization": "Bearer forged"})[0], 401)
        self.assertEqual(self.review()["mission"]["state"], "CRÉÉE")

    def test_claimed_expired_session_cookie_and_replay_are_never_trusted(self):
        self.ready()
        headers = {"Cookie": "session=expired-2000-01-01; authenticated=true; actor=human"}
        for _ in range(2):
            self.assertEqual(self.transition("VALIDÉE", headers=headers)[0], 401)
        self.assertEqual(self.transition("PUBLIÉE", headers=headers)[0], 401)
        code, auth, response_headers = self.request("GET", "/api/auth/status", headers=headers)
        self.assertEqual(code, 200)
        self.assertFalse(auth["authenticated"])
        self.assertFalse(auth["approval_available"])
        self.assertNotIn("Set-Cookie", response_headers)
        serialized = json.dumps(self.review())
        self.assertNotIn("expired-2000", serialized)
        self.assertNotIn("actor=human", serialized)

    def test_csrf_origin_custom_header_host_and_fetch_metadata(self):
        before = self.review()
        for headers in ({"Origin": None}, {"Origin": "null"}, {"Origin": "https://evil.example"},
                        {"X-Orchestra-Request": None}, {"Host": "evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("POST", "/api/projects", {"name": "CSRF"}, headers)[0], 403)
        self.assertEqual(self.request("GET", "/api/snapshot", headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("OPTIONS", "/api/projects")[0], 405)
        self.assertEqual(self.review(), before)

    def test_http_evidence_history_blockers_and_invalidation(self):
        initial = self.review()
        self.assertIn("NON_VÉRIFIÉ", initial["blockers"][0])
        self.assertEqual(self.verify("NON_CONFORME", "Premier essai échoué")[0], 201)
        self.assertIn("NON_CONFORME", self.review()["blockers"][0])
        self.ready()
        ready = self.review()
        self.assertEqual(ready["blockers"], [])
        self.assertEqual(len(ready["verification_history"]), 2)
        self.assertEqual(ready["verification_history"][0]["evidence"], "Premier essai échoué")
        self.assertTrue(ready["criteria"][0]["verified_at"])
        self.assertEqual(self.verify(evidence="Nouveau rapport")[0], 201)
        changed = self.review()
        self.assertEqual(changed["mission"]["state"], "EN_VÉRIFICATION")
        self.assertEqual(changed["mission"]["criteria_revision"], ready["mission"]["criteria_revision"] + 1)
        self.assertEqual(self.request("POST", "/api/transition", {
            "mission_id": self.mission, "target": "ATTENTE_VALIDATION_HUMAINE", "reason": "Stale",
            "expected_revision": ready["mission"]["criteria_revision"]})[0], 409)
        with Registry(self.path) as registry:
            self.assertEqual(registry.mission_review(self.mission), changed)

    def test_stale_revision_refuses_replayed_verification(self):
        revision = self.review()["mission"]["criteria_revision"]
        self.assertEqual(self.verify(revision=revision)[0], 201)
        before = self.review()
        self.assertEqual(self.verify(revision=revision)[0], 409)
        self.assertEqual(self.review(), before)

    def test_free_text_reason_cannot_forge_verification_history(self):
        forged = "Criterion verification: " + json.dumps({"criterion_id": self.criterion,
            "status": "CONFORME", "evidence": "Fake result", "verified_at": "2026-10-30T12:00:00+00:00"})
        self.assertEqual(self.request("POST", "/api/transition", {"mission_id": self.mission,
            "target": "SPÉCIFIÉE", "reason": forged, "expected_revision": 1})[0], 201)
        # A second open must not import the newly supplied text as legacy evidence.
        self.assertEqual(self.review()["verification_history"], [])
        self.assertEqual(self.review()["criteria"][0]["status"], "NON_VÉRIFIÉ")

    def test_concurrent_verifications_only_one_wins(self):
        revision = self.review()["mission"]["criteria_revision"]
        barrier = threading.Barrier(2)

        def verify(index):
            barrier.wait(timeout=5)
            return self.verify(evidence=f"Concurrent result {index}", revision=revision)[0]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(verify, range(2)))
        self.assertEqual(sorted(results), [201, 409])
        review = self.review()
        self.assertEqual(review["mission"]["criteria_revision"], revision + 1)
        self.assertEqual(len(review["verification_history"]), 1)

    def test_concurrent_approval_replays_are_all_refused(self):
        self.ready()
        barrier = threading.Barrier(4)

        def approve(_):
            barrier.wait(timeout=5)
            return self.transition("VALIDÉE", headers={"Authorization": "Bearer reused"})[0]

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(approve, range(4)))
        self.assertEqual(results, [401] * 4)
        review = self.review()
        self.assertEqual(len(review["decisions"]), 4)
        self.assertEqual(review["mission"]["state"], "ATTENTE_VALIDATION_HUMAINE")

    def test_repeated_approval_attempts_are_limited(self):
        for _ in range(10):
            self.assertEqual(self.transition("VALIDÉE")[0], 401)
        code, _, headers = self.transition("VALIDÉE")
        self.assertEqual(code, 429)
        self.assertEqual(headers["Retry-After"], "60")
        self.assertEqual(len(self.review()["decisions"]), 10)

    def test_server_input_validation_and_error_codes(self):
        for evidence in ("", " \n", None, {}, "a" * 8001):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.verify(evidence=evidence)[0], 400)
        self.assertEqual(self.verify(status="PASS")[0], 400)
        for revision in (True, -1, "1", 1.5):
            with self.subTest(revision=revision):
                self.assertEqual(self.verify(revision=revision)[0], 400)
        for raw in (b'{', b'[]', b'{"name":"one","name":"two"}', b'{"name":null}', b'{"name":NaN}', b'\xff'):
            with self.subTest(raw=raw):
                self.assertEqual(self.request("POST", "/api/projects", raw=raw)[0], 400)
        self.assertEqual(self.request("POST", "/api/projects", {"name": "X"}, {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/projects", raw=b'x' * 65537)[0], 413)
        self.assertEqual(self.request("POST", "/missing", {})[0], 404)
        self.assertEqual(self.request("GET", "/api/review/missing")[0], 404)
        self.assertEqual(self.request("POST", "/api/missions", {"project_id": "missing", "title": "X"})[0], 404)
        self.assertEqual(self.request("PUT", "/api/projects", {})[0], 405)
        self.assertEqual(self.review()["criteria"][0]["status"], "NON_VÉRIFIÉ")

    def test_database_failure_is_not_reported_as_approval(self):
        with patch("orchestra.server.Registry", side_effect=sqlite3.OperationalError("locked")):
            self.assertEqual(self.request("POST", "/api/transition", {
                "mission_id": self.mission, "target": "VALIDÉE", "reason": "Attempt", "expected_revision": 1})[0], 503)
        with patch("orchestra.server.Registry", side_effect=RuntimeError("sensitive internals")):
            code, data, _ = self.request("GET", "/api/snapshot")
            self.assertEqual(code, 500)
            self.assertNotIn("sensitive", str(data))
        self.assertEqual(self.review()["mission"]["state"], "CRÉÉE")

    def test_failed_refusal_journal_still_cannot_approve(self):
        with Registry(self.path) as registry:
            registry.db.execute("""CREATE TRIGGER reject_decision BEFORE INSERT ON approval_decisions
                                   BEGIN SELECT RAISE(ABORT, 'journal failed'); END""")
        self.assertEqual(self.transition("VALIDÉE")[0], 409)
        self.assertEqual(self.review()["mission"]["state"], "CRÉÉE")


class RequestLimitTests(unittest.TestCase):
    def test_window_expires_and_parallel_calls_share_limit(self):
        limiter = RequestLimit(2)
        with patch("orchestra.server.time.monotonic", return_value=100):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(lambda _: limiter.allow(), range(8)))
            self.assertEqual(results.count(True), 2)
        with patch("orchestra.server.time.monotonic", return_value=161):
            self.assertTrue(limiter.allow())


if __name__ == "__main__":
    unittest.main()
