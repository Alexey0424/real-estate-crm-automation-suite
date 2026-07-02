#!/usr/bin/env python3
"""
patch_partA_mode_prod.py — GO-LIVE cutover (go-live.md §5). Flip Part A's MODE
variable from TEST -> PROD so every route posts to the REAL channels instead of
the staging-* twins. Marco approved 2026-06-22.

Surgically edits ONLY module 3's MODE variable in the live blueprint; everything
else (10 Slack __IMTCONN__ connections, FUB auth) round-trips unchanged. A full
rebuild would WIPE the Slack connections, so we patch in place.

Usage:  python make/patch_partA_mode_prod.py          # flip to PROD
        python make/patch_partA_mode_prod.py TEST      # roll back to TEST
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA
SID = 5389041

TARGET = (sys.argv[1].upper() if len(sys.argv) > 1 else "PROD")
assert TARGET in ("PROD", "TEST"), "MODE must be PROD or TEST"


def patch(path, body):
    url = f"https://{ZONE}.make.com/api/v2{path}"
    r = urllib.request.Request(url, data=json.dumps(body).encode(), method="PATCH",
        headers={"Authorization": f"Token {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


c, body = m.call(ZONE, f"/scenarios/{SID}/blueprint")
bp = body["response"]["blueprint"] if "response" in body else body

old = None
changed = False
for mod in bp["flow"]:
    if mod.get("module") == "util:SetVariables":
        for v in mod.get("mapper", {}).get("variables", []):
            if v.get("name") == "MODE":
                old = v["value"]; v["value"] = TARGET; changed = True

# safety: confirm slack connections still present (must not be wiped)
conns = sorted({r["flow"][0]["parameters"].get("__IMTCONN__")
                for md in bp["flow"] if md.get("module") == "builtin:BasicRouter"
                for r in md["routes"]})
print(f"MODE: {old} -> {TARGET}")
print("slack connections preserved:", conns)
assert changed, "MODE variable not found — aborting"
assert any(conns) and None not in conns, "a Slack connection is missing — aborting"

code, resp = patch(f"/scenarios/{SID}", {"blueprint": json.dumps(bp)})
print("PATCH:", code, json.dumps(resp)[:140] if isinstance(resp, dict) else resp[:200])
