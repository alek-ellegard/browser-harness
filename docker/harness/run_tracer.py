import json, sys

new_tab("http://frontend/")
wait_for_load(timeout=20)

info = page_info()
print(json.dumps(info))

capture_screenshot(path="/out/screenshot.png", full=True)

# helpers.py prepends a green-circle marker (\U0001F7E2) to the controlled tab's
# title so a human can spot which tab the harness drives — strip it before comparing.
title = info.get("title", "").lstrip("\U0001F7E2 ").strip()
if title != "browser-harness tracer bullet":
    print(f"title mismatch: {info.get('title')!r}", file=sys.stderr)
    sys.exit(1)
if not str(info.get("url", "")).startswith("http://frontend"):
    print(f"url mismatch: {info.get('url')!r}", file=sys.stderr)
    sys.exit(1)
