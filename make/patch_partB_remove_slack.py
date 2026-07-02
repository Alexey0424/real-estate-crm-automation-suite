#!/usr/bin/env python3
"""
patch_partB_remove_slack.py — stop Part B (5390808) from posting its own Slack
notification (Alexey 2026-06-17).

ROOT CAUSE (verified live): Part B was built to post the "New Seller Lead" Slack
message itself, on the premise that "FUB suppresses Part A's webhook for same-system
creates." That premise is FALSE — empirically, Part A's `peopleCreated` webhook DOES
fire on a Part-B-created person (Part A ran 1s after a Part B test submission). So
every cold lead produced TWO Slack posts: Part B's (Lead Manager hardcoded "—") and
Part A's (real Lead Manager from the FUB GET). CLAUDE.md's authoritative design always
said Part A owns the notification — the live build had drifted from it.

FIX: remove Part B's SetVariables (id 5) + Slack (id 6) modules. Part B now ONLY
writes to FUB:  webhook(1) -> POST /v1/events(2) -> POST /v1/notes(3). Part A is the
single new-lead notifier.

Surgical fetch -> filter flow -> PATCH. The two FUB http modules (2,3) round-trip
verbatim, so their inline auth (mapper.authUser) and X-System headers are preserved
(a full overwrite would WIPE the inline key — see memory make-fub-inline-auth).
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA

SID = 5390808
REMOVE_IDS = {5, 6}   # SetVariables (MODE) + Slack (New Seller Lead)


def patch(sid, body):
    url = f"https://{ZONE}.make.com/api/v2/scenarios/{sid}"
    r = urllib.request.Request(url, data=json.dumps(body).encode(), method="PATCH",
        headers={"Authorization": f"Token {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


c, body = m.call(ZONE, f"/scenarios/{SID}/blueprint")
bp = body["response"]["blueprint"] if "response" in body else body

before = [md["id"] for md in bp["flow"]]
fub_auth_before = sum(1 for md in bp["flow"]
                      if "followupboss" in str((md.get("mapper") or {}).get("url", ""))
                      and (md.get("mapper") or {}).get("authUser"))

bp["flow"] = [md for md in bp["flow"] if md.get("id") not in REMOVE_IDS]

after = [md["id"] for md in bp["flow"]]
fub_auth_after = sum(1 for md in bp["flow"]
                     if "followupboss" in str((md.get("mapper") or {}).get("url", ""))
                     and (md.get("mapper") or {}).get("authUser"))

# safety: Slack+SetVars gone, both FUB modules survive WITH inline auth intact
assert 6 not in after and 5 not in after, f"removal failed: {after}"
assert {2, 3}.issubset(set(after)), f"FUB modules missing: {after}"
assert fub_auth_after == fub_auth_before == 2, (
    f"inline auth changed: {fub_auth_before} -> {fub_auth_after}")

code, resp = patch(SID, {"blueprint": json.dumps(bp)})
print(f"flow {before} -> {after} | FUB inline-auth modules {fub_auth_after}/2 preserved | PATCH {code}")
if code not in (200, 201):
    print("RESP", resp)
