"""SQLite-backed project and mission registry. No agent execution in V0.1."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

STATES = ("CRÉÉE", "SPÉCIFIÉE", "PLAN_VALIDÉ", "EN_EXÉCUTION", "EN_VÉRIFICATION", "BLOQUÉE", "ATTENTE_VALIDATION_HUMAINE", "VALIDÉE", "PUBLIÉE", "ANNULÉE", "ÉCHEC_TECHNIQUE", "PUBLICATION_ÉCHOUÉE")
TRANSITIONS = {
    "CRÉÉE": {"SPÉCIFIÉE", "ANNULÉE"},
    "SPÉCIFIÉE": {"PLAN_VALIDÉ", "ANNULÉE"},
    "PLAN_VALIDÉ": {"EN_EXÉCUTION", "ANNULÉE"},
    "EN_EXÉCUTION": {"EN_VÉRIFICATION", "BLOQUÉE", "ÉCHEC_TECHNIQUE"},
    "EN_VÉRIFICATION": {"BLOQUÉE", "ATTENTE_VALIDATION_HUMAINE", "ÉCHEC_TECHNIQUE"},
    "BLOQUÉE": {"EN_EXÉCUTION", "ANNULÉE"},
    "ATTENTE_VALIDATION_HUMAINE": {"VALIDÉE", "BLOQUÉE", "ANNULÉE"},
    "VALIDÉE": {"PUBLIÉE", "PUBLICATION_ÉCHOUÉE"},
    "PUBLICATION_ÉCHOUÉE": {"VALIDÉE", "ANNULÉE"},
    "ÉCHEC_TECHNIQUE": {"EN_EXÉCUTION", "ANNULÉE"},
    "PUBLIÉE": set(),
    "ANNULÉE": set(),
}

def now():
    return datetime.now(timezone.utc).isoformat()

class Registry:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS projects(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, repo TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS missions(
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                title TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS criteria(
                id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(id),
                description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'NON_VÉRIFIÉ'
                CHECK(status IN ('NON_VÉRIFIÉ','CONFORME','NON_CONFORME'))
            );
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL REFERENCES missions(id),
                previous_state TEXT, next_state TEXT NOT NULL,
                reason TEXT NOT NULL, actor TEXT NOT NULL, timestamp TEXT NOT NULL
            );
        """)
        self.db.commit()

    def add_project(self, name, repo=None):
        if not name.strip():
            raise ValueError("Project name required")
        identifier = str(uuid4())
        with self.db:
            self.db.execute("INSERT INTO projects VALUES (?,?,?,?)",
                            (identifier, name.strip(), repo, now()))
        return identifier

    def add_mission(self, project_id, title, actor="human"):
        if not title.strip():
            raise ValueError("Mission title required")
        identifier = str(uuid4())
        with self.db:
            self.db.execute("INSERT INTO missions VALUES (?,?,?,?,?)",
                            (identifier, project_id, title.strip(), "CRÉÉE", now()))
            self.db.execute("INSERT INTO events(mission_id,previous_state,next_state,reason,actor,timestamp) VALUES (?,?,?,?,?,?)",
                            (identifier, None, "CRÉÉE", "Mission created", actor, now()))
        return identifier

    def add_criterion(self, mission_id, description):
        if not description.strip():
            raise ValueError("Criterion description required")
        identifier = str(uuid4())
        with self.db:
            self.db.execute("INSERT INTO criteria(id,mission_id,description) VALUES (?,?,?)",
                            (identifier, mission_id, description.strip()))
        return identifier

    def transition(self, mission_id, target, reason, actor="human"):
        if not reason.strip():
            raise ValueError("Reason required")
        with self.db:
            row = self.db.execute("SELECT state FROM missions WHERE id=?", (mission_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown mission")
            current = row["state"]
            if target not in TRANSITIONS[current]:
                raise ValueError(f"Forbidden transition: {current} -> {target}")
            if target in {"VALIDÉE", "PUBLIÉE"} and actor != "human":
                raise PermissionError("Human approval required")
            if target == "ATTENTE_VALIDATION_HUMAINE":
                failures = self.db.execute(
                    "SELECT COUNT(*) FROM criteria WHERE mission_id=? AND status!='CONFORME'",
                    (mission_id,)).fetchone()[0]
                if failures:
                    raise ValueError("All criteria must be verified as CONFORME")
            self.db.execute("UPDATE missions SET state=? WHERE id=?", (target, mission_id))
            self.db.execute("INSERT INTO events(mission_id,previous_state,next_state,reason,actor,timestamp) VALUES (?,?,?,?,?,?)",
                            (mission_id, current, target, reason.strip(), actor, now()))

    def snapshot(self):
        return {
            "projects": [dict(r) for r in self.db.execute("SELECT * FROM projects ORDER BY created_at")],
            "missions": [dict(r) for r in self.db.execute("SELECT * FROM missions ORDER BY created_at")],
            "criteria": [dict(r) for r in self.db.execute("SELECT * FROM criteria")],
            "events": [dict(r) for r in self.db.execute("SELECT * FROM events ORDER BY id")],
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        self.db.close()
