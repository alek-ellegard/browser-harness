# browser-harness in Docker — Self-Hosted Headless Chrome

Pattern: run headless Chrome as a service exposing CDP, run browser-harness as a separate service pointed at it via `BU_CDP_URL`. Drive a containerized frontend over the compose network. **No third-party services involved.** For Browser Use cloud usage, see `docker-headless-cloud.md`.

## Privacy / data residency (sensitive-data use)

Self-hosted setup keeps all browser traffic and page content inside your network. To verify nothing leaves:

- **Leave `BROWSER_USE_API_KEY` unset.** When unset:
  - `helpers.http_get(url)` uses local `urllib`, not the fetch-use proxy (`src/browser_harness/helpers.py:361-373`).
  - `start_remote_daemon()` is never auto-invoked (`src/browser_harness/run.py:88-89`).
  - Cloud browser shutdown PATCH is skipped (`src/browser_harness/daemon.py:131-143`).
- **Leave `BU_BROWSER_ID` unset.** Only consumed by cloud-shutdown logic.
- **One outbound call remains: the GitHub release check.** `print_update_banner()` (`src/browser_harness/admin.py:499-512`) hits `api.github.com/repos/browser-use/browser-harness/releases/latest` on every CLI invocation, rate-limited to once per 24h via local cache. Page content is never transmitted. To suppress entirely: block `api.github.com` egress from the harness container, or run on an air-gapped network — failures are caught and silently fall back to cache (`admin.py:470-471`).

That is the complete outbound surface in self-hosted mode.

## Connection env vars

| Var | Format | Behavior |
|-----|--------|----------|
| `BU_CDP_URL` | `http://host:port` | Daemon resolves live websocket via `/json/version`; retries 30s while Chrome boots. **Required for the cdp-proxy topology** (see below). Source: `src/browser_harness/daemon.py:81-93`. |
| `BU_CDP_WS` | `ws://host:port/devtools/browser/<uuid>` | Direct websocket. Brittle — UUID changes on Chrome restart. **Incompatible with the cdp-proxy sidecar** (skips `/json/*`, so the `webSocketDebuggerUrl` rewrite never fires). Source: `src/browser_harness/daemon.py:79-80`. |
| `BU_NAME` | string | Namespaces socket/pid/log files (`/tmp/bu-<NAME>.sock`). Use distinct names for parallel agents. |
| `BH_AGENT_WORKSPACE` | path | Override default workspace (`<repo>/agent-workspace`). |

## CDP proxy sidecar (required)

Chromium M111+ enforces DNS-rebinding protection on the DevTools HTTP endpoint: any `/json/*` request whose `Host:` header is not `localhost`/`127.0.0.1` is rejected with HTTP 500. TCP connects, HTTP refuses. Cross-container clients send `Host: chrome:9222` and hit this. The protection is permanent — treat the proxy as canonical topology, not a workaround.

Canonical self-hosted topology is **4 services**: `frontend`, `chrome`, `cdp-proxy`, `harness`. The `cdp-proxy` is a tiny nginx sidecar between `harness` and `chrome` that:

1. `proxy_set_header Host localhost;` — rewrites the inbound Host so Chrome's DevTools endpoint accepts the request.
2. `sub_filter "ws://localhost/" "ws://cdp-proxy:9222/";` on `application/json` — rewrites `webSocketDebuggerUrl` in `/json/*` responses so the harness's WS upgrade flows back through the proxy (which also handles the upgrade).

Harness env: `BU_CDP_URL=http://cdp-proxy:9222`. **Do not use `BU_CDP_WS`** — it bypasses `/json/*` entirely, the `sub_filter` rewrite never fires, and the harness's WS connect targets the wrong host. The daemon resolves the live websocket through `/json/version` (`src/browser_harness/daemon.py:81-93`); that path must run through the proxy.

Working reference: `docker/compose.yaml` (4-service wiring), `docker/cdp-proxy.conf` (25-line nginx config), `docker/README.md` ("Why the cdp-proxy sidecar exists").

## docker-compose pattern

```yaml
services:
  frontend:
    build: ./frontend
    expose: ["80"]

  chrome:
    image: chromedp/headless-shell:latest   # self-hosted, no third-party SaaS
    expose: ["9222"]
    shm_size: "2gb"                         # required: default 64MB /dev/shm crashes Chrome

  cdp-proxy:
    image: nginx:1.27-alpine
    depends_on: [chrome]
    expose: ["9222"]
    volumes:
      - ./cdp-proxy.conf:/etc/nginx/conf.d/default.conf:ro

  harness:
    build: .
    environment:
      BU_CDP_URL: "http://cdp-proxy:9222"   # NOT BU_CDP_WS — must hit /json/* via proxy
      FRONTEND_URL: "http://frontend"
      # BROWSER_USE_API_KEY intentionally unset
    volumes:
      - ./agent-workspace:/app/agent-workspace
    depends_on: [chrome, cdp-proxy, frontend]
```

Minimal `cdp-proxy.conf` (full version in `docker/cdp-proxy.conf`):

```nginx
map $http_upgrade $connection_upgrade { default upgrade; '' close; }
server {
  listen 9222;
  location / {
    proxy_pass http://chrome:9222;
    proxy_set_header Host localhost;          # bypass Chrome DNS-rebinding check
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    sub_filter_types application/json;
    sub_filter_once off;
    sub_filter "ws://localhost/" "ws://cdp-proxy:9222/";  # rewrite webSocketDebuggerUrl
  }
}
```

## Harness Dockerfile

```dockerfile
FROM python:3.13-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY . .
RUN uv tool install -e . && ln -s /root/.local/bin/browser-harness /usr/local/bin/
ENV BH_AGENT_WORKSPACE=/app/agent-workspace
CMD ["browser-harness", "-c", "print(page_info())"]
```

## Driving a test

```bash
docker compose run --rm harness browser-harness -c "
new_tab('http://frontend:3000')
wait_for_load()
print(page_info())
capture_screenshot('/app/agent-workspace/shot.png')
"
```

## Networking matrix

| Harness location | Frontend location | URL to use |
|------------------|-------------------|-----------|
| Container (same compose) | Container | `http://<service-name>:<port>` |
| Container | macOS/Win host | `http://host.docker.internal:<port>` |
| Container | Linux host | `http://172.17.0.1:<port>` or add `extra_hosts: ["host.docker.internal:host-gateway"]` |
| macOS/Win host | Container | `http://localhost:<published-port>` |

## One-shot without compose

```bash
docker run -d --name chrome --rm --shm-size=2g -p 9222:9222 \
  zenika/alpine-chrome --no-sandbox --headless=new \
  --remote-debugging-address=0.0.0.0 --remote-debugging-port=9222 about:blank

BU_CDP_URL=http://localhost:9222 browser-harness -c "
new_tab('http://localhost:3000')
wait_for_load()
capture_screenshot('shot.png')
print(page_info())
"
```

## Required Chrome flags inside Docker

- `--no-sandbox` — required unless host has seccomp/AppArmor configured for Chrome
- `--headless=new` — modern headless mode (old `--headless` lacks features)
- `--disable-gpu` — no GPU in container
- `--remote-debugging-address=0.0.0.0` — bind on all interfaces, not just 127.0.0.1
- `--remote-debugging-port=9222`

## Image options (all self-hosted)

| Image | CDP port | Notes |
|-------|----------|-------|
| `zenika/alpine-chrome` | flag-driven (use `--remote-debugging-port=9222`) | Smallest, plain Chromium. Recommended. |
| `chromedp/headless-shell` | flag-driven | Even smaller, headless-only build. |
| `selenium/standalone-chrome` | 4444 (WebDriver) — not CDP-friendly out of box | Skip unless you need Selenium grid. |
| `ghcr.io/browserless/chromium` | self-hosted **with cloud-style management UI** | Free OSS image; verify license terms before use in commercial product. CDP on internal :3000. |

## Gotchas

- `shm_size: "2gb"` is mandatory. Default 64MB causes random Chrome crashes during heavy DOM ops.
- Headless Chrome has **no profile picker and no "Allow remote debugging" dialog**, so the install.md escalation flow does not apply. `BU_CDP_URL` connects immediately once Chrome is up.
- `daemon.py:128` raises "DevToolsActivePort not found … set BU_CDP_WS for a remote browser" if neither `BU_CDP_URL` nor `BU_CDP_WS` is set — env must be in scope of the `browser-harness` process.
- Use `new_tab(url)` for first navigation, not `goto_url(url)` — convention from `SKILL.md`.
- Default daemon socket is `/tmp/bu-default.sock` inside the container. If running multiple harness processes in one container, set distinct `BU_NAME` per process.
