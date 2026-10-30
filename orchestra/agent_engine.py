"""Local Codex planning adapter. Read-only, explicit CLI invocation; no publishing."""
import json
import os
import shutil
import subprocess
from pathlib import Path

MAX_PROMPT = 12000

class AgentError(RuntimeError):
    pass

def doctor():
    """Report availability without executing Codex."""
    return {"codex": shutil.which("codex"), "git": shutil.which("git")}

def check_workspace(path):
    workspace = Path(path).expanduser().resolve(strict=True)
    if not workspace.is_dir():
        raise AgentError("Workspace must be a directory")
    if not (workspace / ".git").exists():
        raise AgentError("Workspace must be a Git checkout")
    return workspace

def build_plan_command(workspace, prompt):
    """Build a read-only Codex invocation, never via shell=True."""
    workspace = check_workspace(workspace)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise AgentError("Invalid mission brief")
    executable = shutil.which("codex")
    if not executable:
        raise AgentError("Codex CLI not installed or not on PATH")
    return [executable, "exec", "--sandbox", "read-only", "--cd", str(workspace),
            "--", prompt]

def run_plan(workspace, prompt, *, timeout=180):
    """Run ONLY an architect planning task. No edit, approval or Git push."""
    command = build_plan_command(workspace, prompt)
    try:
        result = subprocess.run(command, shell=False, capture_output=True,
                                text=True, timeout=timeout, check=False,
                                stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        raise AgentError("Codex planning timed out") from exc
    if result.returncode:
        raise AgentError((result.stderr or result.stdout or "Codex failed")[-2000:])
    return {"plan": result.stdout[-30000:], "exit_code": result.returncode,
            "mode": "read-only", "workspace": str(check_workspace(workspace))}
