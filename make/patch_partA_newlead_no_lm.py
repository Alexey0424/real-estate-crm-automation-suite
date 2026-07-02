#!/usr/bin/env python3
"""
patch_partA_newlead_no_lm.py — drop the "Lead Manager" line from Part A's (5389041)
NEW-LEAD Slack notification only (Alexey 2026-06-17).

Target: Slack module id 7 (Route 1 "New Seller Lead!", channel {{4.newLeads}}).
Removes the line `Lead Manager: {{5.lead_manager}}` (and its leading newline) so the
post reads Campaign / Seller / Address / FUB Link.

Module 9 ("PREQUALIFIED LEAD ASSIGNED TO YOU") also shows Lead Manager but is the
closer-assignment route, NOT the new-lead notification — it is intentionally left
unchanged. Surgical fetch -> edit mod 7's mapper.text -> PATCH; the Slack connection
and all other modules round-trip untouched. Idempotent.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA

SID = 5389041
LM_LINE = "\nLead Manager: {{5.lead_manager}}"   # leading newline + the line


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


stats = {"edited": 0}


def edit(flow):
    for md in flow:
        if md.get("id") == 7 and md.get("module", "").startswith("slack"):
            mp = md.get("mapper", {}) or {}
            t = mp.get("text", "")
            if LM_LINE in t:
                mp["text"] = t.replace(LM_LINE, "")
                stats["edited"] += 1
        for r in md.get("routes", []) or []:
            edit(r.get("flow", []))


c, body = m.call(ZONE, f"/scenarios/{SID}/blueprint")
bp = body["response"]["blueprint"] if "response" in body else body
edit(bp["flow"])

assert stats["edited"] == 1, f"expected to edit exactly module 7, edited {stats['edited']}"

code, resp = patch(SID, {"blueprint": json.dumps(bp)})
print(f"new-lead Slack (mod 7) Lead-Manager line removed | PATCH {code}")
if code not in (200, 201):
    print("RESP", resp)
