import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from orchestra.agent_engine import AgentError, build_plan_command, check_workspace, run_plan

class AgentEngineTests(unittest.TestCase):
    def test_reject_non_git_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AgentError):
                check_workspace(tmp)

    def test_command_read_only_and_no_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".git").mkdir()
            with patch("orchestra.agent_engine.shutil.which", return_value="/usr/bin/codex"):
                cmd = build_plan_command(tmp, "Analyse et plan")
            self.assertEqual(cmd[1:4], ["exec", "--sandbox", "read-only"])
            self.assertEqual(cmd[-1], "Analyse et plan")

    def test_missing_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".git").mkdir()
            with patch("orchestra.agent_engine.shutil.which", return_value=None):
                with self.assertRaises(AgentError):
                    build_plan_command(tmp, "Plan")

    def test_no_execution_when_prompt_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".git").mkdir()
            with patch("orchestra.agent_engine.shutil.which", return_value="/usr/bin/codex"):
                with self.assertRaises(AgentError):
                    build_plan_command(tmp, "")

    def test_run_uses_subprocess_without_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".git").mkdir()
            class Result:
                returncode = 0
                stdout = "Plan de mission"
                stderr = ""
            with patch("orchestra.agent_engine.shutil.which", return_value="/usr/bin/codex"), patch(
                "orchestra.agent_engine.subprocess.run", return_value=Result()
            ) as run:
                result = run_plan(tmp, "Propose un plan")
            self.assertEqual(result["mode"], "read-only")
            self.assertFalse(run.call_args.kwargs["shell"])
            self.assertEqual(run.call_args.kwargs["timeout"], 180)

if __name__ == "__main__":
    unittest.main()
