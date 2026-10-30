import tempfile
import unittest
from pathlib import Path
from orchestra.core import Registry

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
            self.r.transition(self.mission, "PUBLIÉE", "skip")

    def test_no_unverified_approval(self):
        self.r.add_criterion(self.mission, "Animation verified")
        for state in ("SPÉCIFIÉE", "PLAN_VALIDÉ", "EN_EXÉCUTION", "EN_VÉRIFICATION"):
            self.r.transition(self.mission, state, "progress")
        with self.assertRaises(ValueError):
            self.r.transition(self.mission, "ATTENTE_VALIDATION_HUMAINE", "not tested")

    def test_no_agent_approval(self):
        for state in ("SPÉCIFIÉE", "PLAN_VALIDÉ", "EN_EXÉCUTION", "EN_VÉRIFICATION", "ATTENTE_VALIDATION_HUMAINE"):
            self.r.transition(self.mission, state, "progress")
        with self.assertRaises(PermissionError):
            self.r.transition(self.mission, "VALIDÉE", "agent claim", actor="agent")

if __name__ == "__main__":
    unittest.main()
