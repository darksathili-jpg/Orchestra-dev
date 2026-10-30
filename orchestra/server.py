"""Local-only HTTP dashboard for the V0.1 registry (stdlib, no dependencies)."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from orchestra.core import Registry

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("ORCHESTRA_DB", str(Path.home() / ".orchestra-dev" / "registry.sqlite3")))
HOST = "127.0.0.1"
PORT = int(os.environ.get("ORCHESTRA_PORT", "8766"))

class Handler(BaseHTTPRequestHandler):
    def send(self, status, payload, content_type="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self.send(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/app.js":
            self.send(200, (ROOT / "web" / "app.js").read_bytes(), "text/javascript; charset=utf-8")
        elif path == "/style.css":
            self.send(200, (ROOT / "web" / "style.css").read_bytes(), "text/css; charset=utf-8")
        elif path == "/api/snapshot":
            with Registry(DB) as registry:
                self.send(200, registry.snapshot())
        else:
            self.send(404, {"error": "Not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/api/projects", "/api/missions", "/api/criteria", "/api/transition"):
            return self.send(404, {"error": "Not found"})
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{HOST}:{PORT}":
            return self.send(403, {"error": "Origin not allowed"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 16384:
                return self.send(413, {"error": "Invalid request size"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("JSON object required")
            with Registry(DB) as registry:
                if path == "/api/projects":
                    result = registry.add_project(data["name"], data.get("repo"))
                elif path == "/api/missions":
                    result = registry.add_mission(data["project_id"], data["title"])
                elif path == "/api/criteria":
                    result = registry.add_criterion(data["mission_id"], data["description"])
                else:
                    registry.transition(data["mission_id"], data["target"], data["reason"])
                    result = "ok"
            self.send(201, {"id": result})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.send(400, {"error": str(exc)})
        except Exception:
            self.send(500, {"error": "Internal server error"})

def main():
    print(f"ORCHESTRA DEV: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
