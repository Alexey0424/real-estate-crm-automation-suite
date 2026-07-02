#!/usr/bin/env python3
"""
fetch_slack_channels.py — READ-ONLY: list the workspace's channels + IDs so we
can fill the immutable channel IDs in shared/lib/config.js (routing must use IDs,
not names). Needs a bot token with `channels:read` (+ `groups:read` for private).

Usage:
  SLACK_BOT_TOKEN=xoxb-xxxx python3 fetch_slack_channels.py
Prints the channels the SOW references, with their IDs, and flags any missing.
"""
import os, sys, json, urllib.request, urllib.error, pathlib

try:
    sys.stdout.reconfigure(encoding="utf-8")  # avoid cp1252 crash on Windows console
except Exception:
    pass

WANT = [
    "all-ahb-new-leads", "underwriter-to-dos", "closers-chat", "tc-to-dos",
    "dispo-external-chat", "team-wins", "lead-managers",
    "closer-deals-reyes", "closer-deals-flora", "closer-deals-marco",
]
ROOT = pathlib.Path(__file__).resolve().parents[2]


def token():
    t = os.environ.get("SLACK_BOT_TOKEN")
    if t:
        return t.strip()
    envf = ROOT / ".env" if (ROOT / ".env").exists() else ROOT / ".env.txt"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("SLACK_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    sys.exit("No SLACK_BOT_TOKEN in env or .env.txt")


def call(method, tok, params=""):
    url = f"https://slack.com/api/{method}{params}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    tok = token()
    found, cursor = {}, ""
    while True:
        p = "?limit=1000&types=public_channel,private_channel&exclude_archived=true"
        if cursor:
            p += f"&cursor={cursor}"
        res = call("conversations.list", tok, p)
        if not res.get("ok"):
            sys.exit(f"Slack error: {res.get('error')}")
        for c in res.get("channels", []):
            found[c["name"]] = {"id": c["id"], "private": c.get("is_private", False)}
        cursor = (res.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            break

    print("\n=== CHANNELS REFERENCED BY THE SOW ===")
    for name in WANT:
        if name in found:
            f = found[name]
            tag = "PRIVATE (bot must be invited)" if f["private"] else "public"
            print(f"  ✓ {name:24s} id={f['id']}  [{tag}]")
        else:
            print(f"  ✗ {name:24s} NOT FOUND — create it or check the exact name")


if __name__ == "__main__":
    main()
