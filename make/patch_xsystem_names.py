#!/usr/bin/env python3
"""
patch_xsystem_names.py — rename the FUB integration display name per workflow
(Marco 2026-06-16). FUB shows the X-System header value verbatim on every record an
automation creates (verified live: an unregistered X-System renders as-is; "AHB" is
an alias that renders "Automatic-WorkFlows").

  Part B (5390808) FUB write modules: X-System "AHB" -> "SMS Lead Intake"
  Part C (5396442) FUB modules:       X-System "AHB" -> "Quo Phone Sync"
  Part A (5389041): GET-only, never writes a FUB record -> left as "AHB".

Surgically edits ONLY the X-System header value on http modules whose URL is FUB.
Inline auth (mapper.authUser), bodies, routes, connections all round-trip untouched.
The X-System-Key registration (used for webhook registration under "AHB") is NOT
affected — webhook delivery is independent of record-creation X-System.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA

TARGETS = {5390808: "SMS Lead Intake", 5396442: "Quo Phone Sync"}


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


def set_xsystem(flow, new_val, stats):
    for md in flow:
        mp = md.get("mapper", {}) or {}
        if "followupboss" in str(mp.get("url", "")):
            stats["fub_modules"] += 1
            if mp.get("authUser"):
                stats["auth_ok"] += 1
            for h in (mp.get("headers") or []):
                if str(h.get("name", "")).lower() == "x-system":
                    h["value"] = new_val
                    stats["changed"] += 1
        for r in md.get("routes", []) or []:
            set_xsystem(r.get("flow", []), new_val, stats)


for sid, name in TARGETS.items():
    c, body = m.call(ZONE, f"/scenarios/{sid}/blueprint")
    bp = body["response"]["blueprint"] if "response" in body else body
    stats = {"fub_modules": 0, "changed": 0, "auth_ok": 0}
    set_xsystem(bp["flow"], name, stats)
    # safety: every FUB module must keep inline auth + got the new header
    assert stats["fub_modules"] > 0, f"{sid}: no FUB modules found"
    assert stats["changed"] == stats["fub_modules"], (
        f"{sid}: only {stats['changed']}/{stats['fub_modules']} X-System headers updated")
    assert stats["auth_ok"] == stats["fub_modules"], (
        f"{sid}: inline auth missing on some modules ({stats['auth_ok']}/{stats['fub_modules']})")
    code, resp = patch(sid, {"blueprint": json.dumps(bp)})
    print(f"{sid} -> X-System '{name}': {stats['changed']}/{stats['fub_modules']} modules, "
          f"auth preserved {stats['auth_ok']}/{stats['fub_modules']} | PATCH {code}")
