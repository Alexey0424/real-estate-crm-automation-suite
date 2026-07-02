#!/usr/bin/env python3
"""
fix_partA_fub_auth.py — RECOVERY. Restore the FUB Basic-auth + full http mapper on
Part A's module 2 (the GET /v1/people call), which a generator re-push had stripped
(left only X-System header, no authUser -> BundleValidationError, scenario failing).

Mirrors the proven Part B http:ActionSendData v3 structure (authUser = FUB key,
authPass = blank, full param set) but as a GET with the people lookup URL + qs.
Surgically edits ONLY module 2; Slack connections, channel vars, filters (incl. the
Trash->Lead fix) all round-trip untouched.
"""
import json, urllib.request, urllib.error, importlib.util, pathlib, sys

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone(); TOKEN, UA = m.TOKEN, m.UA
SID = 5389041


def env(k):
    for line in open(ROOT / ".env", encoding="utf-8"):
        s = line.strip()
        if s.lower().startswith(k.lower() + "="):
            return s.split("=", 1)[1].strip()


FUB_KEY = env("FUB_API_KEY")
X_SYSTEM = env("FUB_X_SYSTEM") or "AHB"

MAPPER = {
    "ca": "", "qs": [{"name": "fields", "value": "allFields"}],
    "url": "https://api.followupboss.com/v1/people/{{first(1.resourceIds)}}",
    "data": "", "gzip": True, "method": "get",
    "headers": [{"name": "X-System", "value": X_SYSTEM}],
    "timeout": "", "useMtls": False, "authPass": "", "authUser": FUB_KEY,
    "bodyType": "raw", "contentType": "application/json",
    "serializeUrl": False, "shareCookies": False, "parseResponse": True,
    "followRedirect": True, "useQuerystring": False, "followAllRedirects": False,
    "rejectUnauthorized": True,
}
PARAMS = {"handleErrors": True, "useNewZLibDeCompress": True}


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


assert FUB_KEY, "FUB_API_KEY missing from .env"
c, body = m.call(ZONE, f"/scenarios/{SID}/blueprint")
bp = body["response"]["blueprint"] if "response" in body else body

fixed = False
for md in bp["flow"]:
    if md.get("id") == 2 and md.get("module") == "http:ActionSendData":
        md["parameters"] = PARAMS
        md["mapper"] = MAPPER
        fixed = True

# safety: slack connections must survive
router = [md for md in bp["flow"] if md.get("module") == "builtin:BasicRouter"][0]
conns = sorted({r["flow"][0]["parameters"].get("__IMTCONN__") for r in router["routes"]})
# safety: trash fix must survive
nl = [r["flow"][0] for r in router["routes"] if r["flow"][0]["filter"]["name"] == "New lead"][0]
evs = sorted({x["b"] for grp in nl["filter"]["conditions"] for x in grp if x["a"] == "{{1.event}}"})
print("module 2 restored:", fixed, "| authUser set:", bool(MAPPER["authUser"]))
print("slack connections preserved:", conns)
print("new-lead events preserved:", evs)
assert fixed and conns == [9411588] and "peopleStageUpdated" in evs

code, resp = patch(f"/scenarios/{SID}", {"blueprint": json.dumps(bp)})
print("PATCH:", code, (json.dumps(resp)[:120] if isinstance(resp, dict) else resp[:200]))
