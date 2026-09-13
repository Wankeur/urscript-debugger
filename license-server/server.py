"""Minimal license server for urscript-debugger's premium features.

Pure standard library on purpose — the target deployment is a Synology DS218play
(ARM, no Docker support), so no pip dependencies to manage there.

Endpoints:
  POST /licenses/generate  {admin_token, email}         -> {key}
  POST /licenses/validate  {key, device_id}              -> {valid, reason?}

A license allows up to MAX_ACTIVATIONS distinct device_ids (a simple anti-sharing
measure) — re-validating from an already-seen device_id always succeeds.
"""

import http.server
import json
import os
import secrets
import socketserver
import sqlite3
import urllib.parse

DB_PATH = os.environ.get("LICENSE_DB_PATH", "licenses.db")
ADMIN_TOKEN = os.environ.get("LICENSE_ADMIN_TOKEN")
MAX_ACTIVATIONS = 3


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS licenses (
            key TEXT PRIMARY KEY,
            email TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            revoked INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activations (
            license_key TEXT,
            device_id TEXT,
            activated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(license_key, device_id)
        )
        """
    )
    return conn


class Handler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            body = {}

        if parsed.path == "/licenses/generate":
            self._handle_generate(body)
        elif parsed.path == "/licenses/validate":
            self._handle_validate(body)
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_generate(self, body: dict) -> None:
        if not ADMIN_TOKEN or body.get("admin_token") != ADMIN_TOKEN:
            self._send_json(403, {"error": "forbidden"})
            return

        email = body.get("email", "")
        key = "URSDBG-" + secrets.token_urlsafe(18)
        conn = get_db()
        conn.execute("INSERT INTO licenses (key, email) VALUES (?, ?)", (key, email))
        conn.commit()
        conn.close()
        self._send_json(200, {"key": key})

    def _handle_validate(self, body: dict) -> None:
        key = body.get("key", "")
        device_id = body.get("device_id", "")

        conn = get_db()
        row = conn.execute("SELECT revoked FROM licenses WHERE key = ?", (key,)).fetchone()
        if row is None:
            conn.close()
            self._send_json(200, {"valid": False, "reason": "unknown_key"})
            return
        if row[0]:
            conn.close()
            self._send_json(200, {"valid": False, "reason": "revoked"})
            return

        existing = conn.execute(
            "SELECT 1 FROM activations WHERE license_key = ? AND device_id = ?", (key, device_id)
        ).fetchone()
        if existing is None:
            count = conn.execute(
                "SELECT COUNT(*) FROM activations WHERE license_key = ?", (key,)
            ).fetchone()[0]
            if count >= MAX_ACTIVATIONS:
                conn.close()
                self._send_json(200, {"valid": False, "reason": "activation_limit_reached"})
                return
            conn.execute(
                "INSERT INTO activations (license_key, device_id) VALUES (?, ?)", (key, device_id)
            )
            conn.commit()

        conn.close()
        self._send_json(200, {"valid": True})

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    if not ADMIN_TOKEN:
        print("WARNING: LICENSE_ADMIN_TOKEN not set — /licenses/generate will always refuse.")
    port = int(os.environ.get("PORT", 8080))
    with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
        print(f"License server listening on :{port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
