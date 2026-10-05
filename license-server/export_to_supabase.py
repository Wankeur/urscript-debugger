"""Export the self-hosted license database to SQL for the website's Supabase.

The license server now runs on daedale.eu (Netlify functions + Supabase, see
the wankeur-react-reborn repo). Run this once on the machine that holds the
old database, then paste the output into the Supabase SQL editor:

    python3 export_to_supabase.py /path/to/licenses.db > licenses.sql

Keys, emails, Stripe session ids, revocations and device activations are all
kept, so existing customers don't have to do anything. Re-running the output
is safe: rows that already exist are skipped.
"""

import sqlite3
import sys


def sql_str(value) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "licenses.db"
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    licenses = conn.execute(
        "SELECT key, email, stripe_session_id, created_at, revoked FROM licenses ORDER BY created_at"
    ).fetchall()
    activations = conn.execute(
        "SELECT license_key, device_id, activated_at FROM activations ORDER BY activated_at"
    ).fetchall()

    print("BEGIN;")
    for key, email, session_id, created_at, revoked in licenses:
        print(
            "INSERT INTO public.licenses (key, email, stripe_session_id, created_at, revoked) VALUES "
            f"({sql_str(key)}, {sql_str(email or '')}, {sql_str(session_id)}, "
            f"{sql_str(created_at)}::timestamptz, {'true' if revoked else 'false'}) "
            "ON CONFLICT (key) DO NOTHING;"
        )
    for license_key, device_id, activated_at in activations:
        print(
            "INSERT INTO public.license_activations (license_key, device_id, activated_at) VALUES "
            f"({sql_str(license_key)}, {sql_str(device_id)}, {sql_str(activated_at)}::timestamptz) "
            "ON CONFLICT DO NOTHING;"
        )
    print("COMMIT;")
    print(f"-- {len(licenses)} licenses, {len(activations)} activations", file=sys.stderr)


if __name__ == "__main__":
    main()
