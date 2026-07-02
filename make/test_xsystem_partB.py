#!/usr/bin/env python3
"""
test_xsystem_partB.py — end-to-end proof that Part B now stamps FUB records with
"SMS Lead Intake". Fires the live Part B webhook with a throwaway lead (exactly the
shape google-form/Code.gs sends), reads the created note's systemName, then DELETES
the test person to clean up. Read/verify on FUB; the only residue is a staging Slack
post (harmless).
"""
import sys, json, time, base64, urllib.request, urllib.error, urllib.parse, pathlib

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
def env(k):
    for line in open(ROOT / ".env", encoding="utf-8"):
        s = line.strip()
        if s.lower().startswith(k.lower() + "="): return s.split("=", 1)[1].strip()
KEY = env("FUB_API_KEY")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
WEBHOOK = "https://hook.us2.make.com/xxxxxxxxxxxxxxxxxxxxxxxx"
TEST_PHONE = "+15550100199"  # unique fake number for this test


def fub(path, method="GET"):
    auth = base64.b64encode((KEY + ":").encode()).decode()
    req = urllib.request.Request("https://api.followupboss.com/v1" + path,
        headers={"Authorization": "Basic " + auth, "X-System": "AHB"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


# 1) Build the Code.gs-style payload and fire the live Part B webhook
note_text = ("Cold lead via SMS intake form.\nLead source: SMS - Agent Outreach\n"
             "Notes: systemName verification - safe to delete\nLead Manager: Ethan Rivers")
fub_body = {
    "source": "SMS - Agent Outreach", "system": "AHB", "type": "Registration",
    "message": note_text,
    "person": {"firstName": "Zztest", "lastName": "Systemname", "stage": "Lead",
               "tags": ["Cold Lead - SMS"], "customLeadManager": "Ethan Rivers",
               "phones": [{"value": TEST_PHONE}], "addresses": [{"street": "1 Test St"}]},
}
hook_payload = {
    "payload": json.dumps(fub_body), "noteBodyJson": json.dumps(note_text),
    "firstName": "Zztest", "lastName": "Systemname",
    "source": "SMS - Agent Outreach", "address": "1 Test St", "leadManager": "Ethan Rivers",
}
r = urllib.request.Request(WEBHOOK, data=json.dumps(hook_payload).encode(), method="POST",
    headers={"Content-Type": "application/json", "User-Agent": UA})
with urllib.request.urlopen(r, timeout=30) as resp:
    print("Part B webhook POST ->", resp.status, resp.read().decode()[:30])

# 2) Poll FUB for the created test person
pid = None
for _ in range(8):
    time.sleep(3)
    c, p = fub("/people?" + urllib.parse.urlencode({"phone": TEST_PHONE, "fields": "id,name,source"}))
    if isinstance(p, dict) and p.get("people"):
        pid = p["people"][0]["id"]
        print("created person:", pid, "| name:", p["people"][0].get("name"),
              "| source:", p["people"][0].get("source"))
        break
if not pid:
    print("[ ] test person not found — Part B may not have processed"); sys.exit(1)

# 3) Read the note's systemName
c, n = fub("/notes?" + urllib.parse.urlencode({"personId": pid, "sort": "-created", "limit": 3}))
notes = n.get("notes", []) if isinstance(n, dict) else []
ok = False
for nt in notes:
    print("  note", nt.get("id"), "| systemName:", repr(nt.get("systemName")),
          "| body:", repr(str(nt.get("body", ""))[:45]))
    if nt.get("systemName") == "SMS Lead Intake":
        ok = True

# 4) Clean up — delete the test person (removes its notes too)
c, _ = fub(f"/people/{pid}", "DELETE")
c2, _ = fub(f"/people/{pid}")
print(f"cleanup: DELETE person {pid} -> {c} | confirm gone -> {c2}")

print("\nRESULT:", "[x] Part B stamps 'SMS Lead Intake'" if ok else "[ ] systemName NOT updated")
