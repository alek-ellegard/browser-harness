# Docker tracer bullet

Self-hosted compose stack: a frontend container, a headless Chrome container, and a browser-harness container that drives Chrome to load the frontend and emit a screenshot.

## Run

From this directory (`docker/`):

```sh
docker compose run --rm --build harness
```

Stdout includes a JSON `page_info()` dict. The screenshot is written to `docker/out/screenshot.png` on the host (volume-mounted from `/out` inside the harness).

## Cleanup

```sh
docker compose down -v
```

`out/` is gitignored; remove it manually if you want a clean filesystem too.

## Why `BROWSER_USE_API_KEY` is unset

`src/browser_harness/run.py` only auto-starts a Browser Use cloud session when `BROWSER_USE_API_KEY` is set and no local Chrome is listening. Leaving the variable unset (and `BU_BROWSER_ID` unset) keeps all traffic inside this compose network — no calls to `api.browser-use.com`. The harness reaches Chrome via `BU_CDP_URL=http://cdp-proxy:9222`, which `src/browser_harness/daemon.py` resolves through `/json/version` with a 30s retry budget.

## Why the `cdp-proxy` sidecar exists

Recent Chrome (~M111+) blocks DevTools HTTP requests whose `Host` header is not `localhost`/`127.0.0.1` (DNS-rebinding protection). Across compose service names the harness sends `Host: chrome:9222`, which Chrome rejects with HTTP 500. The `cdp-proxy` nginx service rewrites the inbound `Host` to `localhost`, and rewrites `webSocketDebuggerUrl` in `/json/*` responses so the WS upgrade also flows through the proxy.
