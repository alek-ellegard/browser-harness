# Registering a Custom Site

Two extension points. Pick one or both.

## 1. Domain skill (knowledge / patterns) — markdown

Path: `agent-workspace/domain-skills/<site>/<topic>.md`

Auto-discovery: `goto_url(url)` in `src/browser_harness/helpers.py:163-166` reads the hostname, strips `www.`, takes the first dot-segment, and returns matching `*.md` filenames from `agent-workspace/domain-skills/<segment>/` in its response payload.

```bash
mkdir -p agent-workspace/domain-skills/acme
$EDITOR agent-workspace/domain-skills/acme/scraping.md
```

Hostname → folder mapping:
- `https://news.ycombinator.com/...` → `domain-skills/news/`  (first segment of `news.ycombinator.com`)
- `https://acme.com/...` → `domain-skills/acme/`
- `https://www.acme.com/...` → `domain-skills/acme/`

Capture the durable shape only (per `SKILL.md`):
- URL patterns and required query params
- Private APIs (XHR/fetch endpoints, payload shape, auth)
- Stable selectors (data-*, aria-*, role, semantic classes)
- Framework / interaction quirks
- Waits and the reason they are needed
- Traps and selectors that don't work

Do not write: pixel coordinates, run narration, secrets/cookies/session tokens.

Reference template: `agent-workspace/domain-skills/hackernews/scraping.md` documents three access paths with latency and code examples.

## 2. Site-specific Python helpers — agent_helpers.py

Path: `agent-workspace/agent_helpers.py`

Auto-import: `_load_agent_helpers()` in `src/browser_harness/helpers.py:376-391` imports every non-underscore name from this module into the global namespace of `browser-harness -c '...'` invocations.

```python
# agent-workspace/agent_helpers.py
import json

def acme_login(email, pw):
    new_tab("https://acme.com/login")
    wait_for_load()
    js(f'document.querySelector("#email").value = {json.dumps(email)}')
    click_at_xy(...)
```

Names already in scope (no import needed):
`cdp`, `js`, `goto_url`, `new_tab`, `wait_for_load`, `wait`, `click_at_xy`, `type_text`, `press_key`, `scroll`, `capture_screenshot`, `http_get`, `page_info`, `current_tab`, `list_tabs`, `switch_tab`, `ensure_real_tab`, `iframe_target`, `dispatch_key`, `upload_file`, `drain_events`.

## Pointing at an external workspace

Default workspace: `<repo>/agent-workspace`. Override:

```bash
export BH_AGENT_WORKSPACE=/path/to/your/workspace
```

Resolved in `src/browser_harness/helpers.py:15` and `src/browser_harness/daemon.py:12`. Both `agent_helpers.py` and `domain-skills/` are read from this path.

## Contribution norm

`SKILL.md` "Always contribute back": after a session that learned something non-obvious, open a PR to `agent-workspace/domain-skills/<site>/`. The harness improves only via filed knowledge.
