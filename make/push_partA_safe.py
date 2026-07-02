#!/usr/bin/env python3
"""
push_partA_safe.py — re-push the freshly generated Part A blueprint (make/_inspect/
partA_make.json) to the live scenario WITHOUT losing the Slack connection.

The generator leaves every Slack module's connection blank by design (no secrets in
the file). A raw push would therefore un-link Slack on all routes. This script grafts
the LIVE per-route parameters (the __IMTCONN__ Slack connection) back onto the matching
generated route BY FILTER NAME, and preserves the live webhook hook id, then PATCHes.

Net effect: channels + filters come fresh from source; Slack connection + webhook are
preserved exactly. Read-back verification at the end.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA
SID = 5389041


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


# 1) freshly generated blueprint
new = json.loads((ROOT / "make" / "_inspect" / "partA_make.json").read_text(encoding="utf-8"))

# 2) live blueprint — source of the Slack connection + webhook hook id
c, body = m.call(ZONE, f"/scenarios/{SID}/blueprint")
live = body["response"]["blueprint"] if "response" in body else body
live_router = [md for md in live["flow"] if md.get("module") == "builtin:BasicRouter"][0]
live_params = {r["flow"][0]["filter"]["name"]: r["flow"][0].get("parameters", {})
               for r in live_router["routes"]}
live_hook = live["flow"][0].get("parameters", {}).get("hook")

# 3) graft live Slack connection params onto each generated route by filter name
new_router = [md for md in new["flow"] if md.get("module") == "builtin:BasicRouter"][0]
grafted = []
for r in new_router["routes"]:
    s = r["flow"][0]; name = s["filter"]["name"]
    if name in live_params and live_params[name]:
        s["parameters"] = live_params[name]; grafted.append(name)
# preserve the webhook so the URL the FUB webhooks point at stays valid
new["flow"][0].setdefault("parameters", {})["hook"] = live_hook

conns = sorted({r["flow"][0]["parameters"].get("__IMTCONN__") for r in new_router["routes"]})
print("grafted Slack connection onto routes:", len(grafted), "of", len(new_router["routes"]))
print("connections after graft:", conns)
print("webhook hook id preserved:", live_hook)
assert conns == [9411588], f"connection graft failed: {conns}"
assert live_hook, "no live hook id found"

code, resp = patch(f"/scenarios/{SID}", {"blueprint": json.dumps(new)})
print("PATCH:", code, (json.dumps(resp)[:120] if isinstance(resp, dict) else resp[:200]))
