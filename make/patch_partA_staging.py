#!/usr/bin/env python3
"""
patch_partA_staging.py — point Part A's TEST-mode channels for the 5 routes that
previously had no staging twin (closer x3, team-wins, lead-managers) at the newly
created staging channels, so MODE=TEST is FULLY isolated from real channels.

Surgically edits only module 3's *_test variable values in the live blueprint;
everything else (Slack __IMTCONN__, FUB auth) round-trips unchanged.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA
SID = 5389041

NEW_STAGING = {
    "closerReyes_test":    "C0PORTFOL18",
    "closerFlora_test":   "C0PORTFOL20",
    "closerMarco_test":   "C0PORTFOL21",
    "teamWins_test":     "C0PORTFOL16",
    "leadManagers_test": "C0PORTFOL17",
}


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
changed = []
for mod in bp["flow"]:
    if mod.get("module") == "util:SetVariables":
        for v in mod.get("mapper", {}).get("variables", []):
            if v.get("name") in NEW_STAGING:
                v["value"] = NEW_STAGING[v["name"]]; changed.append(v["name"])

# safety: confirm slack connections still present
conns = sorted({r["flow"][0]["parameters"].get("__IMTCONN__")
                for md in bp["flow"] if md.get("module") == "builtin:BasicRouter"
                for r in md["routes"]})
print("changed:", changed)
print("slack connections preserved:", conns)
assert len(changed) == 5, f"expected 5 updates, got {changed}"

code, resp = patch(f"/scenarios/{SID}", {"blueprint": json.dumps(bp)})
print("PATCH:", code, json.dumps(resp)[:140] if isinstance(resp, dict) else resp[:200])
