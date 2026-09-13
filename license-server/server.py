"""Minimal license server for urscript-debugger's premium features.

Pure standard library on purpose — no pip dependencies to manage on deployment.

Endpoints:
  POST /licenses/generate  {admin_token, email}          -> {key}
  POST /licenses/validate  {key, device_id}               -> {valid, reason?}
  POST /stripe/webhook     (raw Stripe event, signed)      -> {} (200) on success

A license allows up to MAX_ACTIVATIONS distinct device_ids (a simple anti-sharing
measure) — re-validating from an already-seen device_id always succeeds.

The Stripe webhook handles `checkout.session.completed`: generates a key (or
reuses the one already generated for that session, for safe retry/idempotency),
stores it, and emails it to the customer via SMTP.
"""

import email.mime.text
import hashlib
import hmac
import http.server
import json
import os
import secrets
import smtplib
import socketserver
import sqlite3
import time
import urllib.parse

DB_PATH = os.environ.get("LICENSE_DB_PATH", "licenses.db")
ADMIN_TOKEN = os.environ.get("LICENSE_ADMIN_TOKEN")
MAX_ACTIVATIONS = 3

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_SIGNATURE_TOLERANCE_SECONDS = 300

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS licenses (
            key TEXT PRIMARY KEY,
            email TEXT,
            stripe_session_id TEXT UNIQUE,
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


def create_license(conn: sqlite3.Connection, email_addr: str, stripe_session_id: str | None = None) -> str:
    key = "URSDBG-" + secrets.token_urlsafe(18)
    conn.execute(
        "INSERT INTO licenses (key, email, stripe_session_id) VALUES (?, ?, ?)",
        (key, email_addr, stripe_session_id),
    )
    conn.commit()
    return key


def send_license_email(to_addr: str, key: str) -> None:
    if not (SMTP_USER and SMTP_PASSWORD):
        print(f"WARNING: SMTP not configured, cannot email license key to {to_addr}")
        return

    body = (
        "Thanks for purchasing URScript Debugger!\n\n"
        f"Your license key: {key}\n\n"
        "To activate it: open VS Code, run the command "
        '"URScript Debugger: Enter License Key" (Ctrl+Shift+P / Cmd+Shift+P), and paste this key.\n\n'
        "Questions? Just reply to this email."
    )
    msg = email.mime.text.MIMEText(body)
    msg["Subject"] = "Your URScript Debugger license key"
    msg["From"] = SMTP_FROM
    msg["To"] = to_addr

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)


def verify_stripe_signature(raw_body: bytes, sig_header: str) -> bool:
    if not STRIPE_WEBHOOK_SECRET or not sig_header:
        return False

    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        return False

    if abs(time.time() - int(timestamp)) > STRIPE_SIGNATURE_TOLERANCE_SECONDS:
        return False

    signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
    expected = hmac.new(STRIPE_WEBHOOK_SECRET.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


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
        raw_body = self.rfile.read(length) if length else b""

        if parsed.path == "/stripe/webhook":
            self._handle_stripe_webhook(raw_body)
            return

        try:
            body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
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

        conn = get_db()
        key = create_license(conn, body.get("email", ""))
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

    def _handle_stripe_webhook(self, raw_body: bytes) -> None:
        sig_header = self.headers.get("Stripe-Signature", "")
        if not verify_stripe_signature(raw_body, sig_header):
            print("Stripe webhook: invalid signature, rejecting")
            self._send_json(400, {"error": "invalid signature"})
            return

        try:
            event = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid payload"})
            return

        if event.get("type") != "checkout.session.completed":
            self._send_json(200, {"ignored": True})
            return

        session = event["data"]["object"]
        session_id = session.get("id", "")
        customer_email = (session.get("customer_details") or {}).get("email") or session.get("customer_email", "")

        conn = get_db()
        existing = conn.execute(
            "SELECT key FROM licenses WHERE stripe_session_id = ?", (session_id,)
        ).fetchone()
        if existing:
            # Déjà traité (Stripe peut renvoyer le même événement plusieurs fois) : pas de doublon.
            conn.close()
            self._send_json(200, {"already_processed": True})
            return

        key = create_license(conn, customer_email, stripe_session_id=session_id)
        conn.close()

        print(f"Stripe checkout completed: generated {key} for {customer_email}")
        try:
            send_license_email(customer_email, key)
        except Exception as exc:
            # Ne pas faire échouer le webhook si l'email échoue : la clé existe déjà en base,
            # elle peut être renvoyée manuellement. Stripe considère 2xx = "traité".
            print(f"WARNING: failed to email license key to {customer_email}: {exc}")

        self._send_json(200, {"key_generated": True})

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    if not ADMIN_TOKEN:
        print("WARNING: LICENSE_ADMIN_TOKEN not set — /licenses/generate will always refuse.")
    if not STRIPE_WEBHOOK_SECRET:
        print("WARNING: STRIPE_WEBHOOK_SECRET not set — /stripe/webhook will reject everything.")
    if not (SMTP_USER and SMTP_PASSWORD):
        print("WARNING: SMTP_USER/SMTP_PASSWORD not set — license keys won't be emailed.")
    port = int(os.environ.get("PORT", 8080))
    with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
        print(f"License server listening on :{port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
