#!/usr/bin/env python3
"""
patch_partA_address_null.py — fix the "Address: , ,  " render for leads with NO
address (surfaced in live testing 2026-06-16).

Cause: when a person has no address, 2.data.addresses[1].street is null/undefined,
and Make evaluates `null = ""` as FALSE — so every separator (", ", " ") prints
even though all parts are empty. The `= ""` guards only catch literal empty strings.

Fix: wrap every address part in ifempty(...; "") so null normalizes to "" BEFORE the
comparison; an all-empty address then collapses cleanly to "—". Surgically edits
ONLY module 5's `address` variable; routes / Slack conns / FUB auth untouched.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA
SID = 5389041

NEW_ADDR = (
    '{{if(ifempty(2.data.addresses[1].street; "") = ""; "—"; "")}}{{ifempty(2.data.addresses[1].street; "")}}'
    '{{if(ifempty(2.data.addresses[1].city; "") = ""; ""; ", ")}}{{ifempty(2.data.addresses[1].city; "")}}'
    '{{if(ifempty(2.data.addresses[1].state; "") = ""; ""; ", ")}}{{ifempty(2.data.addresses[1].state; "")}}'
    '{{if(ifempty(2.data.addresses[1].code; "") = ""; ""; " ")}}{{ifempty(2.data.addresses[1].code; "")}}'
)


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

fub_auth = next(md.get("mapper", {}).get("authUser") for md in flow if md.get("id") == 2)
changed = False
for md in flow:
    if md.get("id") == 5:
        for v in md["mapper"]["variables"]:
            if v["name"] == "address":
                v["value"] = NEW_ADDR; changed = True

router = [md for md in flow if md.get("module") == "builtin:BasicRouter"][0]
conns = sorted({r["flow"][0]["parameters"].get("__IMTCONN__") for r in router["routes"]})
print("address field updated:", changed)
print("slack connections:", conns, "| FUB inline auth preserved:", bool(fub_auth))
assert changed and conns == [9411588] and fub_auth

code, resp = patch(f"/scenarios/{SID}", {"blueprint": json.dumps(bp)})
print("PATCH:", code, (json.dumps(resp)[:120] if isinstance(resp, dict) else resp[:200]))
