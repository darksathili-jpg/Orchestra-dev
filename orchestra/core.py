"""SQLite registry with evidence gates.

Actor labels are caller declarations, NOT authentication. These guards apply to
Registry operations; they cannot secure a database writable by an untrusted user.
"""
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

class RevisionConflict(ValueError):
    """The criteria changed since the caller examined them."""


class AuthenticationRequired(PermissionError):
    """No trusted authentication provider is available in this release."""


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
            CREATE TABLE IF NOT EXISTS approval_decisions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL REFERENCES missions(id),
                criteria_revision INTEGER NOT NULL, target TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK(outcome='REFUSED'),
                reason TEXT NOT NULL, authenticated_subject TEXT,
                timestamp TEXT NOT NULL
            );
        """)
        # Additive, atomic and repeatable migration; never invent legacy evidence.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in self.db.execute("PRAGMA table_info(criteria)")}
            for column in ("evidence", "verified_at"):
                if column not in columns:
                    self.db.execute(f"ALTER TABLE criteria ADD COLUMN {column} TEXT")
            mission_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(missions)")}
            if "criteria_revision" not in mission_columns:
                self.db.execute("ALTER TABLE missions ADD COLUMN criteria_revision INTEGER NOT NULL DEFAULT 0")
            event_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(events)")}
            for column in ("verification_data", "verification_source"):
                if column not in event_columns:
                    self.db.execute(f"ALTER TABLE events ADD COLUMN {column} TEXT")
            if "verification_data" not in event_columns:
                # Import once. Legacy free text is explicitly marked untrusted.
                for event in self.db.execute("SELECT * FROM events").fetchall():
                    prefixes = ("Criterion verification: ", "Pending approval invalidated. Criterion verification: ")
                    prefix = next((p for p in prefixes if event["reason"].startswith(p)), None)
                    if prefix:
                        try:
                            result = json.loads(event["reason"][len(prefix):])
                            fields = ("criterion_id", "status", "evidence", "verified_at")
                            if not isinstance(result, dict) or any(not isinstance(result.get(k), str) or not result[k].strip() for k in fields):
                                continue
                            if result["status"] not in ("CONFORME", "NON_CONFORME"):
                                continue
                            if not self.db.execute("SELECT id FROM criteria WHERE id=? AND mission_id=?",
                                                   (result["criterion_id"], event["mission_id"])).fetchone():
                                continue
                            self.db.execute("UPDATE events SET verification_data=?,verification_source='legacy-untrusted' WHERE id=?",
                                            (json.dumps({k: result[k] for k in fields}, ensure_ascii=False), event["id"]))
                        except (ValueError, TypeError):
                            continue

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
            self.db.execute("INSERT INTO missions(id,project_id,title,state,created_at) VALUES (?,?,?,?,?)",
                            (identifier, project_id, title.strip(), "CRÉÉE", now()))
            self.db.execute("INSERT INTO events(mission_id,previous_state,next_state,reason,actor,timestamp) VALUES (?,?,?,?,?,?)",
                            (identifier, None, "CRÉÉE", "Mission created", actor, now()))
        return identifier

    def add_criterion(self, mission_id, description, *, expected_revision=None):
        if not description.strip():
            raise ValueError("Criterion description required")
        identifier = str(uuid4())
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            current = self._editable_criteria_state(mission_id)
            self._check_revision(mission_id, expected_revision)
            self.db.execute("INSERT INTO criteria(id,mission_id,description) VALUES (?,?,?)",
                            (identifier, mission_id, description.strip()))
            self._criterion_change(mission_id, current, f"Criterion added: {identifier}", "system")
        return identifier

    def _editable_criteria_state(self, mission_id):
        row = self.db.execute("SELECT state FROM missions WHERE id=?", (mission_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown mission")
        if row["state"] in {"VALIDÉE", "PUBLIÉE", "PUBLICATION_ÉCHOUÉE"}:
            raise ValueError("Criteria are frozen after human approval")
        return row["state"]

    def _criterion_change(self, mission_id, current, reason, actor):
        self.db.execute("UPDATE missions SET criteria_revision=criteria_revision+1 WHERE id=?", (mission_id,))
        target = current
        if current == "ATTENTE_VALIDATION_HUMAINE":
            target = "EN_VÉRIFICATION"
            reason = "Pending approval invalidated. " + reason
            self.db.execute("UPDATE missions SET state=? WHERE id=?", (target, mission_id))
        event = self.db.execute(
            "INSERT INTO events(mission_id,previous_state,next_state,reason,actor,timestamp) VALUES (?,?,?,?,?,?)",
            (mission_id, current, target, reason, actor, now()))
        return event.lastrowid

    def record_verification(self, criterion_id, status, evidence, actor="untrusted", *, expected_revision=None):
        """Store a declared result and UTC date, not an independently proven result.

        Any new result invalidates pending approval, including another CONFORME.
        The event retains previous results when the latest evidence is replaced.
        """
        if status not in ("CONFORME", "NON_CONFORME"):
            raise ValueError("Verification status must be CONFORME or NON_CONFORME")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("Verification evidence required")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT mission_id FROM criteria WHERE id=?", (criterion_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown criterion")
            mission_id = row["mission_id"]
            current = self._editable_criteria_state(mission_id)
            self._check_revision(mission_id, expected_revision)
            verified_at = now()
            self.db.execute("UPDATE criteria SET status=?,evidence=?,verified_at=? WHERE id=?",
                            (status, evidence.strip(), verified_at, criterion_id))
            verification = json.dumps({
                "criterion_id": criterion_id, "status": status,
                "evidence": evidence.strip(), "verified_at": verified_at,
            }, ensure_ascii=False)
            event_id = self._criterion_change(mission_id, current, "Criterion verification: " + verification, actor)
            self.db.execute("UPDATE events SET verification_data=?,verification_source='declared' WHERE id=?",
                            (verification, event_id))

    def _require_verified_criteria(self, mission_id):
        criteria = self.db.execute(
            "SELECT status,evidence,verified_at FROM criteria WHERE mission_id=?",
            (mission_id,)).fetchall()
        if not criteria:
            raise ValueError("At least one acceptance criterion required")
        if any(row["status"] != "CONFORME" or
               any(not isinstance(row[field], str) or not row[field].strip()
                   for field in ("evidence", "verified_at")) for row in criteria):
            raise ValueError("All criteria must be CONFORME with evidence and a verification date")

    def _check_revision(self, mission_id, expected_revision):
        row = self.db.execute("SELECT criteria_revision FROM missions WHERE id=?", (mission_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown mission")
        if expected_revision is not None and (
                type(expected_revision) is not int or expected_revision != row[0]):
            raise RevisionConflict("Les critères ont changé. Rechargez la mission avant de réessayer.")

    def transition(self, mission_id, target, reason, actor="untrusted", *, expected_revision=None):
        if not reason.strip():
            raise ValueError("Reason required")
        # Fail closed for ALL callers, including the HTTP server and actor='human'.
        # The refusal is committed before raising; it must survive rollback of the request.
        if target in {"VALIDÉE", "PUBLIÉE"}:
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                row = self.db.execute("SELECT criteria_revision FROM missions WHERE id=?", (mission_id,)).fetchone()
                if row is None:
                    raise KeyError("Unknown mission")
                self.db.execute(
                    "INSERT INTO approval_decisions(mission_id,criteria_revision,target,outcome,reason,timestamp) "
                    "VALUES (?,?,?,'REFUSED',?,?)",
                    (mission_id, row[0], target, "Authentification humaine isolée indisponible", now()))
            raise AuthenticationRequired("Approbation indisponible : authentification humaine isolée requise.")
        with self.db:
            # Lock before reading: another connection cannot change criteria
            # between the gate check and the state/event writes.
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT state FROM missions WHERE id=?", (mission_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown mission")
            current = row["state"]
            self._check_revision(mission_id, expected_revision)
            if target not in TRANSITIONS[current]:
                raise ValueError(f"Forbidden transition: {current} -> {target}")
            if target in {"ATTENTE_VALIDATION_HUMAINE", "VALIDÉE", "PUBLIÉE"}:
                self._require_verified_criteria(mission_id)
            self.db.execute("UPDATE missions SET state=? WHERE id=?", (target, mission_id))
            self.db.execute("INSERT INTO events(mission_id,previous_state,next_state,reason,actor,timestamp) VALUES (?,?,?,?,?,?)",
                            (mission_id, current, target, reason.strip(), actor, now()))

    def mission_review(self, mission_id):
        """Return a consistent review, without interpreting actor labels as identities."""
        with self.db:
            self.db.execute("BEGIN")
            row = self.db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
            if row is None:
                raise KeyError("Unknown mission")
            mission = dict(row)
            criteria = [dict(r) for r in self.db.execute(
                "SELECT * FROM criteria WHERE mission_id=? ORDER BY rowid", (mission_id,))]
            events = [dict(r) for r in self.db.execute(
                "SELECT * FROM events WHERE mission_id=? ORDER BY id", (mission_id,))]
            decisions = [dict(r) for r in self.db.execute(
                "SELECT * FROM approval_decisions WHERE mission_id=? ORDER BY id", (mission_id,))]
        blockers = [] if criteria else ["Aucun critère d'acceptation."]
        for criterion in criteria:
            missing = []
            if criterion["status"] != "CONFORME":
                missing.append(criterion["status"])
            for field, label in (("evidence", "preuve absente"), ("verified_at", "date absente")):
                if not isinstance(criterion[field], str) or not criterion[field].strip():
                    missing.append(label)
            if missing:
                blockers.append(criterion["description"] + " : " + ", ".join(missing))
        history = []
        for event in events:
            if event["verification_data"]:
                try:
                    result = json.loads(event["verification_data"])
                    if isinstance(result, dict) and {"criterion_id", "status", "evidence", "verified_at"} <= result.keys():
                        history.append({**{key: result[key] for key in ("criterion_id", "status", "evidence", "verified_at")},
                                        "source": event["verification_source"]})
                except (ValueError, TypeError):
                    pass
        return {"mission": mission, "criteria": criteria, "blockers": blockers,
                "verification_history": history, "events": events, "decisions": decisions,
                "approval_available": False,
                "approval_blocker": "Authentification humaine isolée indisponible : approbation et publication bloquées.",
                "allowed_transitions": sorted(TRANSITIONS.get(mission["state"], set()) - {"VALIDÉE", "PUBLIÉE"})}

    def mission_brief(self, mission_id):
        mission = self.db.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
        if mission is None:
            raise KeyError("Unknown mission")
        project = self.db.execute("SELECT * FROM projects WHERE id=?", (mission["project_id"],)).fetchone()
        criteria = [r["description"] for r in self.db.execute(
            "SELECT description FROM criteria WHERE mission_id=? ORDER BY rowid", (mission_id,))]
        lines = [
            "# Mission ORCHESTRA DEV (préparation manuelle)",
            f"Projet : {project['name']}",
            f"Dépôt : {project['repo'] or 'non renseigné'}",
            f"Mission : {mission['title']}",
            f"État : {mission['state']}",
            "",
            "Rôle : architecte. Analyse le projet et propose un plan sans modifier les fichiers.",
            "Ne déclare aucun test réussi sans l'avoir exécuté.",
            "Indique les fichiers concernés, risques, tests et validations humaines nécessaires.",
            "Critères d'acceptation :",
        ]
        lines.extend(f"- {item}" for item in criteria)
        if not criteria:
            lines.append("- Aucun critère défini : demander une spécification avant exécution.")
        return "\n".join(lines)

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
