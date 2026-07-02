#!/usr/bin/env python3
"""
inspect_fub.py — READ-ONLY discovery against Follow Up Boss.

Pulls the exact account-specific values the Slack routing depends on:
  • stages       (route filters must match these EXACTLY)
  • custom fields (confirm the "Lead Manager" key, expected: customLeadManager)
  • users        (closers' exact display names → Reyes/Flora/Marco routing)
  • one sample person (KEYS ONLY, values redacted) to confirm record shape + ID→link

It makes NO writes. Safe to run against production.

Usage:
  # key from env, or from ../../.env.txt as a line: FUB_API_KEY=xxxx
  FUB_API_KEY=xxxx python3 inspect_fub.py
Output goes to docs/_fub-inspection-output/ (gitignored) + a console summary.
"""
import os, sys, json, base64, urllib.request, urllib.error, pathlib

try:
    sys.stdout.reconfigure(encoding="utf-8")  # avoid cp1252 crash on Windows console
except Exception:
    pass

API = "https://api.followupboss.com/v1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "_fub-inspection-output"


def load_key():
    k = os.environ.get("FUB_API_KEY")
    if k:
        return k.strip()
    envf = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("FUB_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("No FUB_API_KEY in env or .env.txt — add it and re-run.")


def get(path, key):
    url = f"{API}{path}"
    auth = base64.b64encode(f"{key}:".encode()).decode()
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {auth}",
        "X-System": "AHB-Automation-Inspect",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:400]}
    except Exception as e:  # noqa
        return {"_error": str(e)}


def main():
    key = load_key()
    OUT.mkdir(parents=True, exist_ok=True)

    stages = get("/stages?limit=100", key)
    customfields = get("/customFields?limit=100", key)
    users = get("/users?limit=100", key)
    people = get("/people?limit=1&fields=allFields", key)

    (OUT / "stages.json").write_text(json.dumps(stages, indent=2))
    (OUT / "customFields.json").write_text(json.dumps(customfields, indent=2))
    (OUT / "users.json").write_text(json.dumps(users, indent=2))

    print("\n=== STAGES (use these EXACT names in route filters) ===")
    for s in (stages.get("stages") or []):
        print(f"  - {s.get('name')!r}  (id={s.get('id')})")

    print("\n=== CUSTOM FIELDS (find 'Lead Manager') ===")
    for c in (customfields.get("customfields") or []):
        print(f"  - label={c.get('label')!r}  name={c.get('name')!r}  type={c.get('type')}")

    print("\n=== USERS (closer display names) ===")
    for u in (users.get("users") or []):
        print(f"  - {u.get('name')!r}  (id={u.get('id')}, role={u.get('role')})")

    print("\n=== SAMPLE PERSON — TOP-LEVEL KEYS ONLY (values redacted, PII-safe) ===")
    arr = people.get("people") or []
    if arr:
        p = arr[0]
        print("  keys:", sorted(p.keys()))
        print("  has 'addresses' array:", isinstance(p.get("addresses"), list))
        print("  has 'customLeadManager':", "customLeadManager" in p)
        print("  sample person id:", p.get("id"),
              "-> confirm browser URL matches https://app.followupboss.com/2/people/view/<id>")
    else:
        print("  (no people returned)", people.get("_error", ""))

    print(f"\nWrote raw JSON to {OUT} (gitignored).")


if __name__ == "__main__":
    main()
