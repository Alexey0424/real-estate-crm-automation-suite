#!/usr/bin/env python3
"""
register_webhooks.py — register FUB webhooks pointing at the Make/n8n endpoint.

NOTE: THIS WRITES TO THE LIVE FUB ACCOUNT. Only run after Alexey/Marco approve, and
only once the receiving URL (Make custom webhook or n8n Webhook node) exists.

Registers:
  • peopleCreated       → fires Route 1 (new lead)
  • peopleStageUpdated  → fires Routes 2–9 + catch-all

Requires registering a System first (apps.followupboss.com/system-registration)
to get X-System / X-System-Key — the X-System-Key also signs webhook deliveries
(FUB-Signature header). Webhooks must be HTTPS and managed by the account owner.

Usage:
  FUB_API_KEY=xxxx X_SYSTEM=AHB-Automation X_SYSTEM_KEY=yyyy \
  TARGET_URL=https://hook.us1.make.com/zzz python3 register_webhooks.py

  # list existing instead of creating:
  ... python3 register_webhooks.py --list
"""
import os, sys, json, base64, urllib.request, urllib.error

API = "https://api.followupboss.com/v1"
EVENTS = ["peopleCreated", "peopleStageUpdated"]


def req(method, path, key, xsys, xkey, body=None):
    auth = base64.b64encode(f"{key}:".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "X-System": xsys,
        "X-System-Key": xkey,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"_body": e.read().decode()[:600]}


def need(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"Missing env {name}")
    return v


def main():
    key = need("FUB_API_KEY")
    xsys = need("X_SYSTEM")
    xkey = need("X_SYSTEM_KEY")

    if "--list" in sys.argv:
        code, body = req("GET", "/webhooks", key, xsys, xkey)
        print(code, json.dumps(body, indent=2))
        return

    target = need("TARGET_URL")
    if not target.startswith("https://"):
        sys.exit("TARGET_URL must be HTTPS")

    for ev in EVENTS:
        code, body = req("POST", "/webhooks", key, xsys, xkey, {"event": ev, "url": target})
        print(f"{ev}: HTTP {code} {json.dumps(body)[:200]}")


if __name__ == "__main__":
    main()
