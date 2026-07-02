#!/usr/bin/env python3
"""
patch_partA_routing_update.py — surgical routing changes requested by Marco/Alexey
(2026-06-16):

  1. NEW route "Offer Rejected" → #closers-chat, fires on stage
     "Offer Rejected - Future Follow Up" (was a no-notify stage). Distinct
     "OFFER REJECTED" message so the team can tell it apart from "OFFER MADE".
  2. "Contract Sent" route → channel changed from #tc-to-dos to #closers-chat.
  3. "Under Contract" left as {{4.dispo}} (= dispo-external-chat in PROD) — already
     what was asked; no change.

Surgical fetch→edit→PATCH so module-2 inline FUB auth + every Slack __IMTCONN__
(9411588) round-trip untouched. The new route clones an existing route's full
parameters to inherit the Slack connection. Read-back asserts before PATCH.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA
SID = 5389041

OFFER_REJECTED_MSG = ("*:x: OFFER REJECTED*\nCloser: {{5.closer}}\n"
                      "Seller Name: {{5.seller_name}}\nAddress: {{5.address}}\n"
                      "FUB Link: {{5.link}}")


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
flow = bp["flow"]
router = [md for md in flow if md.get("module") == "builtin:BasicRouter"][0]
routes = router["routes"]

# guard: capture pre-state
fub_auth_before = next(md.get("mapper", {}).get("authUser") for md in flow if md.get("id") == 2)

# 2) Contract Sent → #closers-chat
contract_changed = False
for r in routes:
    s = r["flow"][0]
    if s["filter"]["name"] == "Contract Sent":
        assert s["mapper"]["channel"] == "{{4.tc}}", "Contract Sent not on tc as expected"
        s["mapper"]["channel"] = "{{4.closersChat}}"
        contract_changed = True

# 1) NEW "Offer Rejected" route — clone an existing route to inherit Slack conn
if not any(r["flow"][0]["filter"]["name"] == "Offer Rejected" for r in routes):
    template = next(r["flow"][0] for r in routes if r["flow"][0]["filter"]["name"] == "Offer Submitted")
    new_id = max(md.get("id", 0) for md in flow
                 for md in ([md] + [x["flow"][0] for x in routes])) + 1
    # robust max id across fixed modules + route modules
    new_id = max([md.get("id", 0) for md in flow] +
                 [r["flow"][0].get("id", 0) for r in routes]) + 1
    new_route = json.loads(json.dumps(template))  # deep copy
    new_route["id"] = new_id
    new_route["filter"] = {"name": "Offer Rejected", "conditions": [
        [{"a": "{{5.stage}}", "b": "Offer Rejected - Future Follow Up", "o": "text:equal:ci"}]]}
    new_route["mapper"]["channel"] = "{{4.closersChat}}"
    new_route["mapper"]["text"] = OFFER_REJECTED_MSG
    new_route["metadata"] = {"designer": {"x": 1800, "y": 1650}}
    routes.append({"flow": [new_route]})
    rejected_added = True
else:
    rejected_added = False

# ── safety read-back ───────────────────────────────────────────────────────
fub_auth_after = next(md.get("mapper", {}).get("authUser") for md in flow if md.get("id") == 2)
conns = sorted({r["flow"][0]["parameters"].get("__IMTCONN__") for r in routes})
names = [r["flow"][0]["filter"]["name"] for r in routes]
cs = next(r["flow"][0]["mapper"]["channel"] for r in routes if r["flow"][0]["filter"]["name"] == "Contract Sent")
orr = next(r["flow"][0]["mapper"]["channel"] for r in routes if r["flow"][0]["filter"]["name"] == "Offer Rejected")

print("Contract Sent changed:", contract_changed, "-> channel:", cs)
print("Offer Rejected added:", rejected_added, "-> channel:", orr)
print("routes now:", len(routes))
print("slack connections:", conns)
print("FUB inline auth preserved:", bool(fub_auth_before) and fub_auth_before == fub_auth_after)

assert contract_changed and cs == "{{4.closersChat}}"
assert orr == "{{4.closersChat}}"
assert conns == [9411588], f"slack conn drift: {conns}"
assert fub_auth_before and fub_auth_before == fub_auth_after, "FUB inline auth would be lost!"
assert names.count("Offer Rejected") == 1

code, resp = patch(f"/scenarios/{SID}", {"blueprint": json.dumps(bp)})
print("PATCH:", code, (json.dumps(resp)[:140] if isinstance(resp, dict) else resp[:200]))
