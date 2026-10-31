"""Local evidence dashboard. Human approval is deliberately unavailable (V0.3.2)."""
import json
import os
import sqlite3
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from orchestra.core import AuthenticationRequired, Registry, RevisionConflict, STATES

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("ORCHESTRA_DB", str(Path.home() / ".orchestra-dev" / "registry.sqlite3")))
HOST = "127.0.0.1"
PORT = int(os.environ.get("ORCHESTRA_PORT", "8766"))


class RequestLimit:
    """Bounded, process-local throttling, not authentication or a DoS boundary."""
    def __init__(self, limit, window=60):
        self.limit, self.window = limit, window
        self.requests = deque()
        self.lock = threading.Lock()

    def allow(self):
        with self.lock:
            stamp = time.monotonic()
            while self.requests and self.requests[0] <= stamp - self.window:
                self.requests.popleft()
            if len(self.requests) >= self.limit:
                return False
            self.requests.append(stamp)
            return True


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, database=DB):
        self.database = Path(database)
        self.write_limit = RequestLimit(120)
        self.approval_limit = RequestLimit(10)
        super().__init__(address, Handler)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Clé JSON dupliquée")
        result[key] = value
    return result


def validate_payload(path, data):
    schemas = {
        "/api/projects": ({"name": 100}, {"repo": 400}),
        "/api/missions": ({"project_id": 80, "title": 160}, {}),
        "/api/criteria": ({"mission_id": 80, "description": 400, "expected_revision": int}, {}),
        "/api/verifications": ({"criterion_id": 80, "status": 30, "evidence": 8000, "expected_revision": int}, {}),
        "/api/transition": ({"mission_id": 80, "target": 40, "reason": 1000, "expected_revision": int}, {}),
    }
    required, optional = schemas[path]
    if not isinstance(data, dict) or not required.keys() <= data.keys() or data.keys() - (required.keys() | optional.keys()):
        raise ValueError("Champs manquants ou non autorisés")
    for key, value in data.items():
        rule = (required | optional)[key]
        if rule is int:
            if type(value) is not int or not 0 <= value <= 9223372036854775807:
                raise ValueError("Version des critères invalide")
        elif not isinstance(value, str) or len(value) > rule or (key not in optional and not value.strip()) or "\x00" in value:
            raise ValueError("Champ invalide : " + key)
    if path == "/api/verifications" and data["status"] not in ("CONFORME", "NON_CONFORME"):
        raise ValueError("Résultat de vérification invalide")
    if path == "/api/transition" and data["target"] not in STATES:
        raise ValueError("État inconnu")
    return data


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self.body_read = 0

    def log_message(self, format, *args):
        # Never log supplied cookies, credentials, bodies or URL query strings.
        pass

    def send(self, status, payload, content_type="application/json; charset=utf-8"):
        if status >= 400:
            # Windows can reset a closing socket with unread inbound data before
            # the client receives the error. Drain only a bounded declared body.
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) == 1 and not self.headers.get("Transfer-Encoding"):
                    remaining = min(max(int(lengths[0]) - self.body_read, 0), 65537)
                    if remaining:
                        self.rfile.read(remaining)
            except (ValueError, OSError):
                pass
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if status == 429:
            self.send_header("Retry-After", "60")
        if status == 405:
            self.send_header("Allow", "GET, POST")
        self.end_headers()
        self.wfile.write(data)

    def permitted_origin(self, write=False):
        for header in ("Host", "Origin", "Content-Type", "Content-Length", "X-Orchestra-Request", "Sec-Fetch-Site"):
            if len(self.headers.get_all(header, [])) > 1:
                return False
        authority = f"{HOST}:{self.server.server_port}"
        if self.headers.get("Host") != authority:
            return False
        origin = self.headers.get("Origin")
        if (write or origin is not None) and origin != "http://" + authority:
            return False
        site = self.headers.get("Sec-Fetch-Site")
        if site not in (None, "same-origin", "none"):
            return False
        return not write or self.headers.get("X-Orchestra-Request") == "1"

    def do_GET(self):
        if not self.permitted_origin():
            return self.send(403, {"error": "Origine non autorisée"})
        path = urlsplit(self.path).path
        try:
            static = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
            if path in static:
                name, mime = static[path]
                return self.send(200, (ROOT / "web" / name).read_bytes(), mime + "; charset=utf-8")
            if path == "/api/auth/status":
                return self.send(200, {"authenticated": False, "approval_available": False,
                                       "reason": "Aucun service d'authentification isolé configuré."})
            with Registry(self.server.database) as registry:
                if path.startswith("/api/brief/"):
                    result = {"brief": registry.mission_brief(path.removeprefix("/api/brief/"))}
                elif path.startswith("/api/review/"):
                    result = registry.mission_review(path.removeprefix("/api/review/"))
                elif path == "/api/snapshot":
                    result = registry.snapshot()
                else:
                    return self.send(404, {"error": "Ressource inconnue"})
            self.send(200, result)
        except KeyError:
            self.send(404, {"error": "Mission inconnue"})
        except sqlite3.OperationalError:
            self.send(503, {"error": "Registre temporairement indisponible"})
        except Exception:
            self.send(500, {"error": "Erreur interne"})

    def do_POST(self):
        if not self.permitted_origin(write=True):
            return self.send(403, {"error": "Origine ou en-tête de requête non autorisé"})
        path = urlsplit(self.path).path
        if path not in ("/api/projects", "/api/missions", "/api/criteria", "/api/verifications", "/api/transition"):
            return self.send(404, {"error": "Ressource inconnue"})
        if not self.server.write_limit.allow():
            return self.send(429, {"error": "Trop de requêtes. Réessayez dans une minute."})
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self.send(415, {"error": "Content-Type application/json requis"})
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Encodage de transfert non pris en charge")
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 65536:
                return self.send(413, {"error": "Taille de requête invalide"})
            body = self.rfile.read(length)
            self.body_read = len(body)
            if len(body) != length:
                raise ValueError("Corps de requête incomplet")
            data = json.loads(body.decode("utf-8"), object_pairs_hook=unique_object)
            validate_payload(path, data)
            if path == "/api/transition" and data["target"] in {"VALIDÉE", "PUBLIÉE"}:
                if not self.server.approval_limit.allow():
                    return self.send(429, {"error": "Trop de tentatives d'approbation. Réessayez dans une minute."})
            with Registry(self.server.database) as registry:
                if path == "/api/projects":
                    result = registry.add_project(data["name"], data.get("repo"))
                elif path == "/api/missions":
                    if not registry.db.execute("SELECT id FROM projects WHERE id=?", (data["project_id"],)).fetchone():
                        raise KeyError("Unknown project")
                    result = registry.add_mission(data["project_id"], data["title"], actor="http-untrusted")
                elif path == "/api/criteria":
                    result = registry.add_criterion(data["mission_id"], data["description"], expected_revision=data["expected_revision"])
                elif path == "/api/verifications":
                    registry.record_verification(data["criterion_id"], data["status"], data["evidence"],
                                                 actor="http-untrusted", expected_revision=data["expected_revision"])
                    result = "ok"
                else:
                    registry.transition(data["mission_id"], data["target"], data["reason"],
                                        actor="http-untrusted", expected_revision=data["expected_revision"])
                    result = "ok"
            self.send(201, {"id": result})
        except AuthenticationRequired as exc:
            self.send(401, {"error": str(exc), "code": "AUTHENTICATION_UNAVAILABLE"})
        except RevisionConflict as exc:
            self.send(409, {"error": str(exc)})
        except KeyError:
            self.send(404, {"error": "Mission, projet ou critère inconnu"})
        except (ValueError, TypeError, UnicodeError) as exc:
            self.send(400, {"error": str(exc)})
        except sqlite3.IntegrityError:
            self.send(409, {"error": "Conflit de données"})
        except sqlite3.OperationalError:
            self.send(503, {"error": "Registre temporairement indisponible"})
        except Exception:
            self.send(500, {"error": "Erreur interne"})

    def unsupported(self):
        self.send(405, {"error": "Méthode non autorisée"})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = unsupported


def main():
    print(f"ORCHESTRA DEV: http://{HOST}:{PORT} — approbation désactivée")
    Server((HOST, PORT)).serve_forever()


if __name__ == "__main__":
    main()
