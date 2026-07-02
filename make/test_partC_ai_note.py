#!/usr/bin/env python3
"""
test_partC_ai_note.py — live test of Part C's AI-summary route (scenario 5396442).

Fires a jc.call_ai_generated webhook (JustCall shape) at the Part C Make URL for a
chosen FUB person's phone, polls the Make execution log for success, then reads that
person's FUB Notes and prints the newest note so we can eyeball the formatting.

Side effect: creates ONE real FUB note on the target person. Use a TEST contact.
Pass --cleanup to delete the note this run created (notes ARE API-deletable).

Usage:
  python make/test_partC_ai_note.py <personId> <phone> [--cleanup]
  e.g. python make/test_partC_ai_note.py 265849 1234567890
"""
import sys, json, time, base64, urllib.request, urllib.error, importlib.util, pathlib

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("m", ROOT / "make" / "make_api.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ZONE, _ = m.find_zone()

SID = 5396442
HOOK = "https://hook.us2.make.com/xxxxxxxxxxxxxxxxxxxxxxxx"


def env(k):
    for line in (ROOT / ".env").read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s.startswith(k + "=") and not s.startswith("#"):
            return s.split("=", 1)[1].strip()
    return None


FUB_KEY = env("FUB_API_KEY")
FUB_AUTH = "Basic " + base64.b64encode((FUB_KEY + ":").encode()).decode()


def fub(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.followupboss.com/v1" + path, data=data,
        method=method, headers={"Authorization": FUB_AUTH, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_err": e.read().decode()[:300]}


def fire(phone):
    payload = {
        "request_id": "test-partc-ai",
        "type": "jc.call_ai_generated",
        "data": {
            "id": 999000111,
            "contact_number": phone,
            "contact_name": "Bob Smith Test",
            "justcall_number": "+13055550100",
            "agent_id": 79,
            "agent_name": "Flora",
            "agent_email": "flora@acmehomebuyers.example",
            "call_info": {"direction": "Outgoing", "type": "answered"},
            "call_duration": {"total_duration": 142, "friendly_duration": "00:02:22"},
            "justcall_ai": {
                "call_summary": ("Call Summary:\n"
                                 "1. Marco offered $100,000 for the house and confirmed the terms.\n"
                                 "2. Alexey agreed to sell the house.\n"
                                 "3. The paperwork will take about one week to close.\n"
                                 "Action Items:\n"
                                 "1. Follow up with the underwriter and send the paperwork."),
                "action_items": "",
                "customer_sentiment": "Positive",
            },
        },
    }
    body = json.dumps(payload).encode()
    r = urllib.request.Request(HOOK, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": m.UA})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, resp.read().decode()[:40]


def latest_execs(limit=8):
    _, lg = m.call(ZONE, f"/scenarios/{SID}/logs?pg[limit]={limit}")
    return [(x["id"], x.get("status"), x.get("operations"))
            for x in (lg.get("scenarioLogs") or []) if x.get("eventType") == "EXECUTION_END"]


def wait_for_new(seen, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for eid, st, ops in latest_execs():
            if eid not in seen:
                seen.add(eid); return eid, st, ops
        time.sleep(2)
    return None, None, None


def newest_note(pid):
    code, d = fub("GET", f"/notes?personId={pid}&sort=-created&limit=1&fields=id,subject,body,created")
    notes = d.get("notes") or []
    return notes[0] if notes else None


pid = int(sys.argv[1]); phone = sys.argv[2]
cleanup = "--cleanup" in sys.argv

before = newest_note(pid)
before_id = before["id"] if before else None
seen = {e[0] for e in latest_execs(20)}

print(f"Firing jc.call_ai_generated for person {pid} (phone {phone})…")
code, _ = fire(phone)
print("  webhook POST:", code)

eid, st, ops = wait_for_new(seen)
if eid is None:
    print("  NOTE: no Make execution seen (timeout)"); sys.exit(1)
print(f"  Make exec {eid}: status={st} ops={ops}  ({'OK' if st == 1 else 'ERROR'})")

time.sleep(2)
after = newest_note(pid)
if not after or after["id"] == before_id:
    print("  [ ] no new note created"); sys.exit(1)

print("\n--- NEW FUB NOTE ---")
print("id:     ", after["id"])
print("created:", after.get("created"))
print("subject:", after.get("subject"))
print("body:")
print(after.get("body"))
print("--- END ---")

if cleanup:
    c, _ = fub("DELETE", f"/notes/{after['id']}")
    print(f"\ncleanup: deleted note {after['id']} (HTTP {c})")
