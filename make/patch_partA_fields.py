#!/usr/bin/env python3
"""
patch_partA_fields.py — surgically fix Part A's field map (module 5) so empty
Address / Lead Manager render as a clean em-dash instead of bare commas.

Fetches the LIVE blueprint (which already carries the user's Slack __IMTCONN__
links + FUB Basic auth) and rewrites ONLY module 5's `address` + `lead_manager`
values, then PATCHes it back — connections untouched.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone()
TOKEN, UA = m.TOKEN, m.UA
SID = 5389041

DASH = "—"  # em-dash
# Adjacency + literal-returning if(): each segment adds its separator only when
# present; an all-empty address collapses to just the em-dash.
ADDRESS = (
    f'{{{{if(2.data.addresses[1].street = ""; "{DASH}"; "")}}}}'
    '{{2.data.addresses[1].street}}'
    '{{if(2.data.addresses[1].city = ""; ""; ", ")}}{{2.data.addresses[1].city}}'
    '{{if(2.data.addresses[1].state = ""; ""; ", ")}}{{2.data.addresses[1].state}}'
    '{{if(2.data.addresses[1].code = ""; ""; " ")}}{{2.data.addresses[1].code}}'
)
LEAD_MANAGER = f'{{{{ifempty(2.data.customLeadManager; "{DASH}")}}}}'


def patch(path, body):
    url = f"https://{ZONE}.make.com/api/v2{path}"
    r = urllib.request.Request(url, data=json.dumps(body).encode(), method="PATCH",
        headers={"Authorization": f"Token {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(r, timeout=40) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


code, body = m.call(ZONE, f"/scenarios/{SID}/blueprint")
bp = body["response"]["blueprint"] if "response" in body else body
changed = []
for mod in bp["flow"]:
    if mod.get("id") == 5:
        for v in mod["mapper"]["variables"]:
            if v["name"] == "address":
                v["value"] = ADDRESS; changed.append("address")
            elif v["name"] == "lead_manager":
                v["value"] = LEAD_MANAGER; changed.append("lead_manager")
assert set(changed) == {"address", "lead_manager"}, f"only changed {changed}"

# sanity: connections still present in the blueprint we're about to send back
conns = [r["flow"][0]["parameters"].get("__IMTCONN__")
         for mod in bp["flow"] if mod.get("module") == "builtin:BasicRouter"
         for r in mod["routes"]]
print("slack connections in blueprint:", sorted(set(conns)))

code, resp = patch(f"/scenarios/{SID}", {"blueprint": json.dumps(bp)})
print("PATCH:", code, json.dumps(resp)[:200] if isinstance(resp, dict) else resp[:200])
