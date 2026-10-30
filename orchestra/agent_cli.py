"""Explicit local CLI for a read-only architect plan."""
import argparse
import json
import sys
from orchestra.agent_engine import AgentError, doctor, run_plan

def main():
    parser = argparse.ArgumentParser(description="ORCHESTRA DEV local agent bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check local tools")
    plan = sub.add_parser("plan", help="Run Codex architect in read-only mode")
    plan.add_argument("--workspace", required=True, help="Existing local Git checkout")
    plan.add_argument("--brief-file", required=True, help="UTF-8 mission brief file")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            result = doctor()
        else:
            from pathlib import Path
            result = run_plan(args.workspace, Path(args.brief_file).read_text(encoding="utf-8"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (AgentError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
