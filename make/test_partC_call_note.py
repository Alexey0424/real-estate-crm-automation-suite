#!/usr/bin/env python3
"""
test_partC_call_note.py — end-to-end test of Part C's NEW custom call note.

Creates a throwaway FUB person, fires JustCall's two-step webhook sequence at the live
Part C URL (call.completed → basic note, then jc.call_ai_generated → enriched note),
reads the resulting FUB call note, then deletes the person (calls aren't API-deletable,
but deleting the person cascades to its calls — keeps production clean).

Usage:  python make/test_partC_call_note.py
"""
import sys, json, time, base64, urllib.request, urllib.error, importlib.util, pathlib

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

HOOK = "https://hook.us2.make.com/xxxxxxxxxxxxxxxxxxxxxxxx"
PHONE = "15550199001"          # distinctive throwaway number
SID = "CAtest0000partc0000callnote0001"


def env(k):
    for line in (ROOT / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith(k + "=") and not s.startswith("#"):
            return s.split("=", 1)[1].strip()
    return None


AUTH = "Basic " + base64.b64encode((env("FUB_API_KEY") + ":").encode()).decode()


def fub(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.followupboss.com/v1" + path, data=data,
        method=method, headers={"Authorization": AUTH, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_err": e.read().decode()[:200]}


def fire(payload):
    r = urllib.request.Request(HOOK, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": m.UA})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status


BASE = {
    "id": 999111222, "call_sid": SID, "contact_number": PHONE,
    "contact_name": "PartC Note Test", "justcall_number": "15550120001",
    "agent_id": 1, "agent_name": "Marco Diaz", "agent_email": "marco@acmehomebuyers.example",
    "call_info": {"direction": "Outgoing", "type": "answered", "recording": "https://rec.example/x"},
    "call_duration": {"total_duration": 139, "friendly_duration": "00:02:19"},
}
AI = dict(BASE, justcall_ai={
    "call_score": 73,
    "call_moments": ["Discovery Questions", "Objections", "Process"],
    "customer_sentiment": "Neutral",
    "call_summary": ("Call Summary:\n1. The buyer is willing to offer up to $100,000.\n"
                     "2. The paperwork will take about a week.\n"
                     "Action Items:\n1. Send the paperwork via email.\n"
                     "2. Follow up with a call in about three hours."),
})


# create throwaway person
code, resp = fub("POST", "/events", {"source": "Test", "system": "AHB", "type": "General Inquiry",
    "person": {"firstName": "PartC", "lastName": "NoteTest", "phones": [{"value": PHONE}]}})
pid = resp.get("id") or (resp.get("person") or {}).get("id")
print("created test person:", pid, "| phone", PHONE)
time.sleep(1)

print("\n1) fire call.completed ...", fire({"type": "call.completed", "data": BASE}))
time.sleep(6)
print("2) fire jc.call_ai_generated ...", fire({"type": "jc.call_ai_generated", "data": AI}))
time.sleep(7)

code, d = fub("GET", f"/calls?personId={pid}&sort=-created&limit=1&fields=id,note,duration,created")
calls = d.get("calls") or []
if calls:
    print("\n--- FUB CALL NOTE (enriched) ---")
    print(calls[0].get("note"))
    print("--- END ---")
else:
    print("\n  no call found:", d)

# cleanup: delete person (cascades to its calls)
c, _ = fub("DELETE", f"/people/{pid}")
print(f"\ncleanup: deleted test person {pid} (HTTP {c})")
