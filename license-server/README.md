# license-server

Minimal license validation server for urscript-debugger's premium features. Pure Python standard library — no dependencies to install.

## Endpoints

- `POST /licenses/generate` — `{admin_token, email}` → `{key}`. Requires `LICENSE_ADMIN_TOKEN` to match.
- `POST /licenses/validate` — `{key, device_id}` → `{valid, reason?}`. Called by the extension. Each key allows up to 3 distinct `device_id`s.

## Running locally

```bash
LICENSE_ADMIN_TOKEN=dev-token PORT=8080 python3 server.py
```

## Running via Docker

```bash
docker build -t urscript-license-server .
docker run -d --name urscript-license-server --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -e LICENSE_ADMIN_TOKEN=<your-admin-token> -e PORT=8080 \
  -v $(pwd)/data:/data \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
  urscript-license-server
```

The container runs as a non-root user with a read-only filesystem (except `/data` and `/tmp`) and no Linux capabilities — a public-facing service should never have more access than it needs.

Deployment-specific notes (which machine, how it's exposed publicly) are kept out of this public repo — see `DEPLOY.md` locally (git-ignored).
