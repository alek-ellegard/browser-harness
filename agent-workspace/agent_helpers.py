"""Agent-editable browser helpers.

Add task-specific browser primitives here. Core helpers from browser_harness.helpers
load this file when BH_AGENT_WORKSPACE points at this directory, or when this
repo's default agent-workspace exists.
"""

import json
import os

# Core helpers live in browser_harness.helpers; this module is exec'd as its own
# module (its functions' __globals__ is this file), so the core primitives must be
# imported by name to be in scope here — they are not injected the other direction.
from browser_harness.helpers import cdp, js, capture_screenshot, new_tab, wait_for_load


# Measures every Mermaid `.nodeLabel` in the current page and reports horizontal
# overflow. Returns a JSON string (json.loads it on the Python side).
#   - inlineColor: the value of the label's *inline* `style="color:…"`. Mermaid
#     serialises a classDef `color:` to an inline `!important`, which outranks any
#     stylesheet rule — so a non-empty value here is unfixable from CSS and is
#     illegible in whichever scheme the hardcoded ink clashes with. Hard fail.
#   - contrast: WCAG ratio of computed text color vs the node's (alpha-composited)
#     fill. Secondary signal for un-classed / default labels.
_MEASURE_JS = r"""
(function () {
  function parse(s) {
    if (!s) return null;
    var m = s.match(/rgba?\(([^)]+)\)/i);
    if (!m) return null;
    var p = m[1].split(',').map(parseFloat);
    return [p[0] || 0, p[1] || 0, p[2] || 0, p.length > 3 ? p[3] : 1];
  }
  function lum(c) {
    var a = c.slice(0, 3).map(function (v) {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
  }
  function over(fg, bg) {
    var a = fg[3];
    return [fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a), fg[2] * a + bg[2] * (1 - a), 1];
  }
  function ratio(c1, c2) {
    var l1 = lum(c1), l2 = lum(c2), hi = Math.max(l1, l2), lo = Math.min(l1, l2);
    return (hi + 0.05) / (lo + 0.05);
  }
  var pageBg = parse(getComputedStyle(document.body).backgroundColor)
    || parse(getComputedStyle(document.documentElement).backgroundColor) || [255, 255, 255, 1];
  var pb = pageBg[3] < 1 ? over(pageBg, [255, 255, 255, 1]) : pageBg;
  var labels = Array.prototype.slice.call(document.querySelectorAll('.mermaid .nodeLabel'));
  var out = labels.map(function (el, i) {
    var cs = getComputedStyle(el);
    var color = parse(cs.color) || [0, 0, 0, 1];
    var nodeG = el.closest('.node') || el.closest('.label-container') || el.parentElement;
    var shape = nodeG ? nodeG.querySelector('rect,polygon,circle,ellipse,path') : null;
    var fill = shape ? parse(getComputedStyle(shape).fill) : null;
    var eff = fill ? (fill[3] < 1 ? over(fill, pb) : fill) : pb;
    return {
      i: i,
      text: (el.textContent || '').slice(0, 40),
      inlineColor: el.style.color || '',
      inlinePriority: el.style.getPropertyPriority('color') || '',
      color: cs.color,
      fill: shape ? getComputedStyle(shape).fill : null,
      contrast: Math.round(ratio(color, eff) * 100) / 100
    };
  });
  var de = document.documentElement;
  var wide = Array.prototype.slice.call(document.querySelectorAll('*'))
    .filter(function (e) { return e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 2; })
    .slice(0, 8)
    .map(function (e) {
      var c = e.className && e.className.baseVal !== undefined ? e.className.baseVal : (e.className || '');
      return { tag: e.tagName.toLowerCase(), cls: String(c).slice(0, 40), over: e.scrollWidth - e.clientWidth };
    });
  return JSON.stringify({ labels: out, overflow: de.scrollWidth > de.clientWidth + 2, wide: wide });
})()
"""


def audit_visualize_html(url=None, screenshot_dir="/tmp"):
    """Deterministic readability lint for a visualize-skill HTML page.

    Loads `url` in a fresh tab (or audits the current tab if url is None), then
    forces `prefers-color-scheme` to light and dark in turn. For each scheme it
    measures every Mermaid `.nodeLabel` and screenshots the page, then resets the
    media emulation so the user's browser is not left overridden.

    Findings (each {severity, rule, scheme, msg}):
      - error / mermaid-inline-color: label carries an inline `color:` — the
        classDef `color:` trap. Scheme-independent, unbeatable by CSS. The fix is
        to remove `color:` from the classDef so the label inherits the
        theme-aware `themeVariables.primaryTextColor`.
      - warn / low-contrast: computed text vs node-fill contrast < 3:1.
      - warn / horizontal-overflow: page overflows its width in that scheme.

    Returns {url, ok, findings, schemes} where ok is False iff any error finding.
    Screenshots land at <screenshot_dir>/ve-audit-<scheme>.png.
    """
    if url:
        new_tab(url)
        wait_for_load()

    schemes = {}
    findings = []
    for idx, scheme in enumerate(("light", "dark")):
        cdp("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": scheme}])
        data = json.loads(js(_MEASURE_JS))
        data["screenshot"] = capture_screenshot(os.path.join(screenshot_dir, f"ve-audit-{scheme}.png"), full=True)
        schemes[scheme] = data

        for lab in data["labels"]:
            # inline color is scheme-independent — report it once (first pass).
            if lab["inlineColor"] and idx == 0:
                bang = " !important" if lab["inlinePriority"] == "important" else ""
                findings.append({
                    "severity": "error", "rule": "mermaid-inline-color", "scheme": "both",
                    "msg": f"nodeLabel[{lab['i']}] {lab['text']!r} has inline color:{lab['inlineColor']}{bang} "
                           f"(classDef color: trap — no CSS override can win; remove it from the classDef)",
                })
            elif not lab["inlineColor"] and lab["contrast"] < 3.0:
                findings.append({
                    "severity": "warn", "rule": "low-contrast", "scheme": scheme,
                    "msg": f"nodeLabel[{lab['i']}] {lab['text']!r} contrast {lab['contrast']}:1 (<3:1) — "
                           f"text {lab['color']} on fill {lab['fill']}",
                })
        if data["overflow"]:
            findings.append({
                "severity": "warn", "rule": "horizontal-overflow", "scheme": scheme,
                "msg": f"page overflows horizontally in {scheme}: {data['wide'][:3]}",
            })

    cdp("Emulation.setEmulatedMedia", features=[])  # reset
    ok = not any(f["severity"] == "error" for f in findings)
    return {"url": url, "ok": ok, "findings": findings, "schemes": schemes}
