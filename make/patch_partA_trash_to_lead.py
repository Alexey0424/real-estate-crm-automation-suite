#!/usr/bin/env python3
"""
patch_partA_trash_to_lead.py — make the "New lead" route fire on a move INTO the
"Lead" stage (e.g. a lead recovered from Trash), not only on first creation.

Before: event == "peopleCreated"  AND stage == "Lead"
After:  (event == "peopleCreated" OR event == "peopleStageUpdated") AND stage == "Lead"

Encoded as two Make OR-groups, each AND-ing stage == "Lead" with one event, so a
future webhook type (e.g. peopleUpdated) can't spam the channel. Surgically edits
only the New-lead route's filter in the live blueprint; Slack __IMTCONN__ + FUB
auth round-trip unchanged.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA
SID = 5389041

STAGE = {"a": "{{5.stage}}", "b": "Lead", "o": "text:equal:ci"}
NEW_CONDITIONS = [
    [{"a": "{{1.event}}", "b": "peopleCreated", "o": "text:equal"}, STAGE],
    [{"a": "{{1.event}}", "b": "peopleStageUpdated", "o": "text:equal"}, STAGE],
]


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
router = [md for md in bp["flow"] if md.get("module") == "builtin:BasicRouter"][0]

changed = False
for r in router["routes"]:
    s = r["flow"][0]
    if s.get("filter", {}).get("name") == "New lead":
        s["filter"]["conditions"] = NEW_CONDITIONS
        changed = True

# safety: confirm slack connections still present on every route
conns = sorted({r["flow"][0]["parameters"].get("__IMTCONN__") for r in router["routes"]})
print("New-lead route updated:", changed)
print("slack connections preserved:", conns)
assert changed, "New lead route not found"
assert conns == [9411588], f"unexpected slack connections: {conns}"

code, resp = patch(f"/scenarios/{SID}", {"blueprint": json.dumps(bp)})
print("PATCH:", code, json.dumps(resp)[:140] if isinstance(resp, dict) else resp[:200])
