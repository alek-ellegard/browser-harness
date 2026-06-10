# agent-workers — spawn & monitor a task via the operator web UI

Drive the local **agent-workers operator dashboard** to spawn a durable `gh-overstory-task`
(clone a repo → Overstory swarm implements → build/test → open a PR) and monitor it.
This is a **localhost-only** dev dashboard, so a cloud browser cannot reach it — use a local
browser (Way 2 below).

## Prerequisites (the stack must be up)

The dashboard is served by the `web` compose service. From the agent-workers checkout/worktree:

```bash
docker compose up -d --build postgres web   # + the per-language worker(s) you target
curl -s http://localhost:8080/api/health     # -> {"ok":true,...}
```

- Dashboard: `http://localhost:8080`
- Workers are **per-language**: `agent-worker-python` claims queue `agent-python`, `agent-worker-go`
  claims `agent-go`. The spawn's `language` selection routes the task to `agent-<language>`.
  The matching worker must be running or the task is never claimed.

## Connection: use Way 2 (isolated Chrome on a FREE port)

The dashboard is loopback-only, so a Browser Use cloud browser can't see it. The user's everyday
Chrome (Way 1) needs the chrome://inspect "Allow remote debugging" popup clicked, which an agent
can't do. So launch a dedicated debug Chrome:

```bash
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
nohup "$CHROME" --remote-debugging-port=9333 --user-data-dir="$HOME/.cache/bh-profile" \
  --no-first-run --no-default-browser-check "http://localhost:8080" >/tmp/bh-chrome.log 2>&1 & disown
curl -s --retry 25 --retry-delay 1 --retry-connrefused http://127.0.0.1:9333/json/version   # wait for CDP
export BU_CDP_URL=http://127.0.0.1:9333        # set for every browser-harness call
```

- **TRAP — port 9222 is often already taken.** The user's real Chrome (Way-1 checkbox) binds
  `127.0.0.1:9222`; if you also launch on 9222 your instance only gets `[::1]:9222` and
  `curl 127.0.0.1:9222` hits the wrong (popup-blocked) Chrome. **Use a free port (9333)** and a
  **non-default `--user-data-dir`** (Chrome 136+ silently no-ops the port flag on the default profile dir).
- `--user-data-dir="$HOME/.cache/bh-profile"` is a throwaway profile; fine, the dashboard needs no login.

## Spawn form (`POST /api/spawn`)

Fields (all `required`), by `name`:

| name | element | notes |
|---|---|---|
| `repo_url` | input | accepts `owner/repo`; the form expands it to `https://github.com/owner/repo.git` on submit. The input **normalizes a pasted full URL down to `owner/repo`** for display. |
| `base_branch` | input | the **stable trunk that holds the PRD** (e.g. `main`/`master`). The worker validates the PRD here and cuts the work branch from it. |
| `agent_branch` | input | the work branch (PR head); created from `base_branch` if absent on origin. |
| `prd_path` | input | path to the PRD **on `base_branch`** (e.g. `prd/go-add.md`). Missing PRD on base = hard pre-flight fail. |
| `language` | **select** | options `["", "python", "go"]`, **REQUIRED**. Omitting it → backend **HTTP 400 "language: Required"** (`.strict()` zod enum). Selecting it routes to queue `agent-<language>`. |

**Private API (faster than the DOM if you don't need the UI):**
`POST /api/spawn` JSON body `{repo_url, base_branch, agent_branch, prd_path, language}` →
`{ok, task_id, stdout, stderr, exit_code}`. `GET /api/tasks` → `{tasks:[{task_id, repo, agent_branch, age_s, status, language?}]}` (polled every 5s by the rail).

### TRAP — the cascade gate wipes sibling fields on *trusted* edits

The form clears downstream fields when a controlling field changes via a **trusted** event:
`repo_url` change → clears `base_branch`/`agent_branch`/`prd_path`; `base_branch` change → clears
`agent_branch`/`prd_path`. The handler is gated on `event.isTrusted`.

Two safe ways to fill:
1. **Fill top-down with trusted input** (`repo_url` first, then base, agent, prd) so each cascade
   only clears not-yet-filled fields.
2. **Fill via DOM with synthetic events** (`isTrusted:false` → cascade suppressed, values still land
   in the DOM and `new FormData(form)` reads them at submit). This is the simplest for automation:

```python
js("""(() => {
  const set=(n,v)=>{const e=document.querySelector(`[name="${n}"]`);e.value=v;
    e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));};
  set('repo_url','owner/repo');           // owner/repo form — the submit path expands it
  set('base_branch','main');
  set('agent_branch','feat/my-work');
  set('prd_path','prd/thing.md');
  set('language','go');                    // must match a running agent-worker-<language>
})()""")
```

### Submit — there is no geometric `button[type=submit]`

Looking for a submit button by geometry fails (`getBoundingClientRect` → 0×0; its text reads empty).
Submit the form element directly:

```python
js("(()=>{document.querySelector('[name=repo_url]').closest('form').requestSubmit();})()")
```

The receipt area then renders **`exit 0 · <ms>`**, the `Task ID: <uuid>`, `Run ID`, `Attempt`, and an
**"Open in Habitat ↗"** link. Poll `document.body.innerText` for `Task ID:\s*([0-9a-f-]{36})`.
A 400 instead shows `<field>: <message>` (e.g. `language: Required`).

## Monitoring through the UI

- **RUNNING TASKS rail** (right column) polls `GET /api/tasks` every 5s and shows a card per running
  task: repo + `agent_branch` + age.
- **GAP — the rail card does NOT show language/queue** (the backend carries it; the card doesn't
  render it), so you can't visually confirm a task's language post-spawn from the rail alone.
- **GAP — the in-dashboard tmux embed is python-worker-only.** Only `agent-worker-python` maps ttyd
  `:7682`; `agent-worker-go` runs headless. So a **go** task's `ov-dashboard` embed won't load in the
  UI (deferred multi-worker embed). Verify go tasks out-of-band (below).

## Out-of-band verification (more reliable than the UI for completion)

```bash
docker compose logs -f agent-worker-go      # look for: "build/test: lang=go cmd=go test ./..." then "PR created: <url>"
uvx absurdctl dump-task --task-id <id>       # run history; see TRAP below
gh pr list --repo <owner>/<repo> --head <agent_branch>   # the delivered PR
```

The delivered PR body carries a **`Build/test (<lang>): <cmd> — passed`** block (the worker's own
in-process build/test result).

### TRAP — Overstory coordinator cold-start "zombie" → first attempt fails, Absurd retries

The first attempt frequently fails at the first `ov mail` dispatch with
`Recipient "coordinator" is in terminal state (zombie)` (a known Overstory startup race). Absurd
retries (`max-attempts 2`) and **attempt 2 usually completes**. Consequence:
`absurdctl list-tasks` may summarize the task as `failed (2/2)` even while a later run **completed** —
**read the per-run history in `dump-task`, not the summary line.** A completed run logs
`delegation finished: status=completed, finalized=True` then the build/test + PR.

## Reset between e2e runs (keep the target repo clean)

Each run leaves a pushed `agent_branch` + an open PR against `base_branch`. For a repeatable test,
either reuse one `agent_branch` (PR delivery is idempotent — it updates the existing PR) or close the
PR + delete the branch afterward:

```bash
gh pr close <n> --repo <owner>/<repo> --delete-branch
```
