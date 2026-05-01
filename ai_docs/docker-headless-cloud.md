# browser-harness in Docker — Browser Use Cloud

For when you want a hosted, isolated cloud browser instead of running headless Chrome yourself. **Sends page traffic and content through `api.browser-use.com`** — not appropriate for company-internal sites with sensitive data; use `docker-headless.md` instead.

## When to choose cloud over self-hosted

- Bot-detection bypass via residential proxies
- Geo-located browsing (proxy country code)
- No infra to manage; pay per browser-hour
- Profiles persist cookies across runs (cloud-side state)

## Required env vars

| Var | Behavior |
|-----|----------|
| `BROWSER_USE_API_KEY` | Auth for `api.browser-use.com/api/v3`. Required. |
| `BU_BROWSER_ID` | Cloud browser UUID. Set automatically by `start_remote_daemon()`; daemon shutdown PATCHes `/browsers/{id}` with `{"action":"stop"}` to release the cloud browser (`src/browser_harness/daemon.py:131-143`). |
| `BU_CDP_WS` | Set automatically by `start_remote_daemon()` from the cloud browser's `cdpUrl` (`src/browser_harness/admin.py:353`). |
| `BU_NAME` | Distinct per parallel agent — each cloud browser is its own session. |

## Auto-provision pattern (recommended)

If `BROWSER_USE_API_KEY` is set and no local Chrome is listening, `browser-harness -c '...'` calls `start_remote_daemon(NAME)` automatically (`src/browser_harness/run.py:88-89`). Single env var = working setup.

```yaml
services:
  harness:
    build: .
    environment:
      BROWSER_USE_API_KEY: ${BROWSER_USE_API_KEY}
      BU_NAME: "work"
    volumes:
      - ./agent-workspace:/app/agent-workspace
```

```bash
docker compose run --rm harness browser-harness -c "
new_tab('https://example.com')
wait_for_load()
print(page_info())
"
```

## Explicit provisioning (when you need profile / proxy / timeout)

```bash
browser-harness -c "
start_remote_daemon('work')                                       # clean browser
# start_remote_daemon('work', profileName='my-work')              # reuse cloud profile (logged-in state)
# start_remote_daemon('work', profileId='<uuid>')                 # same, by UUID
# start_remote_daemon('work', proxyCountryCode='de', timeout=120) # DE proxy, 2-hour timeout
# start_remote_daemon('work', proxyCountryCode=None)              # disable Browser Use proxy
"
```

`start_remote_daemon` prints `liveUrl` for human watch-along. The daemon PATCHes the cloud browser to stop on shutdown — profile state persists, billing stops at timeout.

## Cloud profiles (cookie-only login state)

```bash
browser-harness -c "
print(list_cloud_profiles())                # list profiles under current API key
sync_local_profile('my-work')               # upload local Chrome profile cookies → cloud
"
```

`sync_local_profile()` shells out to `profile-use sync` (v1.0.4+); requires `BROWSER_USE_API_KEY`. See `interaction-skills/profile-sync.md` in the harness repo for the chat-driven "which profile?" pattern.

## Cost / lifecycle

- Cloud browsers bill until timeout or explicit stop.
- `browser-harness` daemon shutdown auto-stops the cloud browser via `_stop_cloud_browser()` (`admin.py:251`).
- If a daemon dies unexpectedly, the cloud browser keeps running until `timeout` (default 120s, configurable).

## Networking notes

- Cloud `cdpUrl` is **HTTPS, not ws**. Daemon resolves the websocket via `/json/version` (`admin.py:_cdp_ws_from_url`).
- Browser Use API is camelCase on the wire (`cdpUrl`, `proxyCountryCode`, `profileId`).
- Stop endpoint: `PATCH /browsers/{id}` body `{"action": "stop"}`.
- API base: `https://api.browser-use.com/api/v3` (`daemon.py:62`, `admin.py:33`).

## No cdp-proxy sidecar in cloud mode

The `cdp-proxy` nginx sidecar described in `docker-headless.md` is **not needed here**. Cloud Chrome is reached over WSS at the URL Browser Use returns in `cdpUrl`; the harness connects to that remote endpoint directly, so the cross-container `Host: chrome:9222` situation that triggers Chrome's DNS-rebinding rejection in self-hosted compose does not apply. For the self-hosted 4-service topology (`frontend` + `chrome` + `cdp-proxy` + `harness`), see `docker-headless.md`.

## Hybrid pitfall

Setting `BROWSER_USE_API_KEY` while also pointing `BU_CDP_URL` at a self-hosted Chrome causes:
- `helpers.http_get(url)` to silently route through the fetch-use proxy instead of local urllib (`helpers.py:361-373`).

For self-hosted-only behavior, leave `BROWSER_USE_API_KEY` unset.
