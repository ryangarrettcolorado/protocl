#!/usr/bin/env python3
"""
Safely persist a Strava connector response to disk as valid JSON.

Reads a JSON payload from stdin (either a bare list of activities OR an object
shaped like {"result": [...]}), validates it, and writes it to the target path
in the canonical `{"result": [...]}` shape that load_strava.py expects.

Usage from cron:
    python3 protocl/scripts/save_strava_raw.py < /tmp/strava_response.json

Or with an explicit output path:
    python3 protocl/scripts/save_strava_raw.py /path/to/out.json < input.json

Why this exists:
    The `write` tool in the cron environment truncates large payloads (~64KB).
    A 14-day Strava pull with 50 activities can exceed that limit. This helper
    streams stdin straight to disk via json.dump(), so size is bounded only by
    available disk space, and the output is always valid JSON regardless of
    polyline / unicode content in any string field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "ryan" / "_strava_raw.json"


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raw = sys.stdin.read()
    if not raw.strip():
        print("ERROR: empty stdin", file=sys.stderr)
        return 2

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: stdin is not valid JSON: {e}", file=sys.stderr)
        return 3

    # Normalize to {"result": [...]}
    if isinstance(payload, list):
        activities = payload
    elif isinstance(payload, dict) and isinstance(payload.get("result"), list):
        activities = payload["result"]
    elif isinstance(payload, dict) and isinstance(payload.get("activities"), list):
        activities = payload["activities"]
    else:
        print(
            f"ERROR: unexpected payload shape: {type(payload).__name__}; "
            "expected list or dict with 'result' / 'activities' key",
            file=sys.stderr,
        )
        return 4

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"result": activities}, f, ensure_ascii=False)

    # Re-validate by reloading.
    with open(out_path, encoding="utf-8") as f:
        reloaded = json.load(f)
    n = len(reloaded.get("result", []))
    size_kb = out_path.stat().st_size / 1024
    print(f"OK: wrote {n} activities to {out_path} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
