# Visualize HTML — Readability Audit

`http://visualize.localhost:<port>/<file>.html` — self-contained HTML diagrams
produced by a visualization skill (cc-marketplace `visual-explainer` /
`visualize` commands). Covers auditing their readability across color schemes.
Does NOT cover authoring the HTML (that lives in the cc-marketplace skill).

## Do this first

```python
r = audit_visualize_html("http://visualize.localhost:8001/your-diagram.html")
print(r["ok"], r["findings"])          # ok is False iff any error-severity finding
# screenshots at /tmp/ve-audit-light.png and /tmp/ve-audit-dark.png
```

`audit_visualize_html` (in `agent-workspace/agent_helpers.py`) forces
`prefers-color-scheme` light **and** dark, measures every Mermaid `.nodeLabel`,
checks horizontal overflow, screenshots each scheme, then resets the media
emulation. It is deterministic and low-cost — prefer it over eyeballing.

## Why `visualize.localhost` (the serving convention)

A local `file://` HTML has no hostname, so the harness's `goto_url` domain-skill
hook (which keys on the URL hostname) can't surface this skill. Serving the file
under the `visualize` subdomain fixes that:

```bash
serve your-diagram.html --label visualize      # → http://visualize.localhost:<port>/your-diagram.html
```

- `*.localhost` resolves to loopback on macOS/Chrome with no `/etc/hosts` entry.
- The static server ignores the `Host` header, so serving is identical to plain
  `localhost`; only the hostname the browser navigates to changes.
- `goto_url("http://visualize.localhost:<port>/…")` then returns
  `domain_skills: ["readability-audit.md", …]` — this file surfaces itself.

## Trap: Mermaid `classDef color:` is unbeatable by CSS

The single most common readability bug in these diagrams. **A `classDef` (or
per-node `style`) that sets `color:` makes the label text illegible in one
scheme and no CSS can rescue it.**

Mermaid serializes that `color:` to an *inline* `style="color:…!important"` on
the label `<span class="nodeLabel">`. An inline `!important` outranks every
stylesheet rule — including a `.mermaid .nodeLabel { color: var(--text)
!important }` override — because inline wins on specificity even against
`!important`. So the hardcoded ink (e.g. dark `#16263d`) stays put and vanishes
on a dark node fill (~1:1 contrast).

`audit_visualize_html` flags this as `rule: "mermaid-inline-color"` (error)
whenever a label's inline `style.color` is non-empty.

**Fix (the only one that works):** remove `color:` from the classDef entirely.
The label then inherits the theme-aware `themeVariables.primaryTextColor`, set
via an `isDark ? darkInk : lightInk` ternary in `mermaid.initialize(...)` — which
is exactly why that variable must be set. A CSS override cannot substitute for
removing the classDef color.

```
classDef trace fill:#b07d2026,stroke:#b07d20,stroke-width:2px;   ✅ no color:
classDef trace fill:#b07d20,color:#16263d;                       ❌ inline !important trap
```

## What the audit checks

| rule | severity | meaning |
| --- | --- | --- |
| `mermaid-inline-color` | error | label has inline `color:` (classDef trap) — scheme-independent |
| `low-contrast` | warn | computed text vs node-fill contrast < 3:1 (WCAG) in that scheme |
| `horizontal-overflow` | warn | page overflows its width in that scheme (check `wide` for the culprits) |

## Manual probe (when the helper isn't enough)

```python
cdp("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
# inspect: which labels carry an inline color (the trap)?
js("return [...document.querySelectorAll('.mermaid .nodeLabel')].map(e => e.style.color).filter(Boolean)")
cdp("Emulation.setEmulatedMedia", features=[])   # always reset so the user's browser isn't left overridden
```

Pass `features` as a **kwarg**, not a positional dict — `cdp(method,
session_id=None, **params)` would otherwise read the dict as `session_id`.
