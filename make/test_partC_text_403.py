#!/usr/bin/env python3
"""
test_partC_text_403.py — does FUB accept a 2nd integration's POST /v1/textMessages
now that JustCall's NATIVE SMS logging is turned OFF?

Background: when JustCall native text logging was ON, FUB returned 403 for Part C's
`POST /v1/textMessages` (FUB locks text logging to one registered "system"). We just
disabled native SMS logging in JustCall (Workflow Settings → Log incoming/outgoing SMS
= Disabled, account-wide). This probes whether that releases the lock.

Faithful to Part C: sends the SAME `X-System: JustCall Phone Sync` header the live FUB
modules use (that header is the integration identity FUB was blocking).

Creates a throwaway person, POSTs one incoming + one outgoing text, prints each HTTP
status + body, then deletes the person (cascades to its texts). No live scenario needed.

Usage:  python make/test_partC_text_403.py
"""
import sys, json, time, base64, urllib.request, urllib.error, pathlib

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
PHONE = "15550199042"            # distinctive throwaway number
AHB_LINE = "15550120001"         # an AHB JustCall line (our number)


def env(k):
    for line in (ROOT / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith(k + "=") and not s.startswith("#"):
            return s.split("=", 1)[1].strip()
    return None


AUTH = "Basic " + base64.b64encode((env("FUB_API_KEY") + ":").encode()).decode()
X_SYSTEM = env("FUB_X_SYSTEM_PARTC") or "JustCall Phone Sync"


def fub(method, path, body=None, x_system=False):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": AUTH, "Content-Type": "application/json"}
    if x_system:
        headers["X-System"] = X_SYSTEM
    r = urllib.request.Request("https://api.followupboss.com/v1" + path, data=data,
                               method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_err": e.read().decode()[:400]}


# create throwaway person
code, resp = fub("POST", "/events", {"source": "Test", "system": "AHB", "type": "General Inquiry",
    "person": {"firstName": "PartC", "lastName": "TextTest", "phones": [{"value": PHONE}]}})
pid = resp.get("id") or (resp.get("person") or {}).get("id")
print(f"created test person: {pid} | phone {PHONE} | X-System='{X_SYSTEM}'")
time.sleep(1)

# incoming text (lead -> us): fromNumber=lead, toNumber=AHB line
incoming = {"personId": pid, "message": "Hi this is OneClickSMS.io (Main), test inbound.",
            "isIncoming": True, "fromNumber": "+" + PHONE, "toNumber": "+" + AHB_LINE}
# outgoing text (us -> lead)
outgoing = {"personId": pid, "message": "Test outbound from AHB.",
            "isIncoming": False, "fromNumber": "+" + AHB_LINE, "toNumber": "+" + PHONE}

for label, payload in (("INCOMING", incoming), ("OUTGOING", outgoing)):
    code, body = fub("POST", "/textMessages", payload, x_system=True)
    verdict = "OK [x]" if code in (200, 201) else ("403 BLOCKED [ ]" if code == 403 else f"HTTP {code}")
    print(f"\n{label} textMessages POST -> {verdict}")
    print("  ", json.dumps(body)[:400])

# cleanup
c, _ = fub("DELETE", f"/people/{pid}")
print(f"\ncleanup: deleted test person {pid} (HTTP {c})")
