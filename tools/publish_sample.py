"""Copy a run's dashboard + report into docs/sample_dashboard (redacted).

Usage:
    python tools/publish_sample.py --job ragevda_output_offline_demo

Copies dashboard.html + report.json; redacts URLs containing tokens in
RAGEVDA_REDACT_SUBSTR (comma-separated, default: token,secret,key).
Stdlib only so CI stays green.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", default="ragevda_output_offline_demo")
    ap.add_argument("--out", default=os.path.join("docs", "sample_dashboard"))
    args = ap.parse_args()
    src_html = os.path.join(args.job, "dashboard.html")
    src_json = os.path.join(args.job, "report.json")
    if not os.path.exists(src_html):
        print(f"no dashboard at {src_html}; run the offline demo first")
        return 1
    os.makedirs(args.out, exist_ok=True)
    shutil.copyfile(src_html, os.path.join(args.out, "dashboard.html"))
    if os.path.exists(src_json):
        redact = [s.strip().lower() for s in
                  os.environ.get("RAGEVDA_REDACT_SUBSTR", "token,secret,key").split(",") if s.strip()]
        try:
            with open(src_json, encoding="utf-8") as fh:
                data = json.load(fh)
            prov = data.get("provenance", []) or []
            kept = [p for p in prov
                    if not any(r in str(p.get("url", "")).lower() for r in redact)]
            data["provenance"] = kept
            with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except Exception as exc:  # noqa: BLE001
            print(f"report copy skipped: {exc}")
    print(f"sample published to {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
